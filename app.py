"""
FraudLens v2 — an agentic fraud investigator on FalkorDB.

WeMakeDevs x FalkorDB "Graph Hacks" — Track 01: Agents That Act on Connected Data.

The agent has three READ-ONLY tools (each returns the exact Cypher it ran, so
the UI can show the graph doing the work) and one WRITE action:

    POST /api/tools/trace_hops   — multi-hop money trail from an account
    POST /api/tools/find_ring    — shared device + IP fraud-ring detection
    POST /api/tools/pagerank_hub — PageRank over TRANSFERRED edges (mule hubs)
    POST /api/actions/freeze     — THE ACTION: freezes accounts, writes a
                                   (:Case)-[:TARGETS]->(:Account) case file

Safety rails:
    * Tool queries are regex-guarded to be read-only; freeze is the ONLY
      write path in the whole API.
    * FalkorDB Cloud works via FALKOR_HOST / FALKOR_PORT / FALKOR_USER /
      FALKOR_PASSWORD env vars (empty password = local Docker, no auth).
"""
import logging
import os
import re
import time
from random import randint

from falkordb import FalkorDB
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ---------------------------------------------------------------- config

GRAPH = os.getenv("FALKOR_GRAPH", "fraudlens")
HOST = os.getenv("FALKOR_HOST", "localhost")
PORT = int(os.getenv("FALKOR_PORT", "6379"))
USER = os.getenv("FALKOR_USER", "default")
PASSWORD = os.getenv("FALKOR_PASSWORD", "")          # empty -> local, no auth
SOCKET_TIMEOUT = float(os.getenv("FALKOR_SOCKET_TIMEOUT", "20"))  # seconds

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s [fraudlens] %(message)s")
log = logging.getLogger("fraudlens")


def _client_kwargs() -> dict:
    kw: dict = {"host": HOST, "port": PORT,
                "socket_connect_timeout": 10, "socket_timeout": SOCKET_TIMEOUT}
    if PASSWORD:  # FalkorDB Cloud (or any ACL-secured instance)
        kw["username"] = USER
        kw["password"] = PASSWORD
    return kw


_db = None  # constructed lazily so the API boots even if FalkorDB is down


def get_db() -> FalkorDB:
    """Lazily build (and cache) the FalkorDB client.

    falkordb>=1.5 connects eagerly in __init__, so constructing at import
    time would crash `uvicorn app:app` whenever the database isn't up yet.
    Lazy construction means the app always boots and endpoints return clean
    502s instead.
    """
    global _db
    if _db is None:
        _db = FalkorDB(**_client_kwargs())
        log.info("FalkorDB client connected: %s:%d graph=%s auth=%s",
                 HOST, PORT, GRAPH, "password" if PASSWORD else "none")
    return _db

app = FastAPI(title="FraudLens",
              description="Agentic fraud investigator — the graph decides, then acts.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.time()
    try:
        resp = await call_next(request)
    except Exception:
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        raise
    ms = (time.time() - started) * 1000
    log.info("%s %s -> %d (%.1f ms)", request.method, request.url.path,
             resp.status_code, ms)
    return resp


# ------------------------------------------------------- Cypher helpers

# Write keywords are forbidden inside the three read-only tools. Freeze is
# the only sanctioned write path (it goes through run_write, not run_tool).
_WRITE_RE = re.compile(
    r"\b(SET|CREATE|DELETE|DETACH|MERGE|DROP|REMOVE|LOAD)\b", re.IGNORECASE)


def assert_readonly(cypher: str) -> None:
    """Refuse to run anything that mutates the graph through a tool endpoint."""
    if _WRITE_RE.search(cypher):
        raise HTTPException(
            400, "Blocked: write query sent to a read-only tool. "
                 "The only write path is POST /api/actions/freeze.")


def cols_of(result):
    """Header entries vary per client version:
    [(name, type), ...], [(type, name), ...], or [name, ...].
    Always pick the string element = the column name."""
    cols = []
    for h in result.header:
        if isinstance(h, (list, tuple)):
            name = next((x for x in h if isinstance(x, str)), h[0])
            cols.append(name)
        else:
            cols.append(h)
    return cols


def _path_parts(path):
    """falkordb-py exposes .nodes/.edges as methods in some versions,
    properties in others — handle both so the UI never breaks."""
    nodes = path.nodes() if callable(getattr(path, "nodes", None)) else path.nodes
    edges = path.edges() if callable(getattr(path, "edges", None)) else path.edges
    return nodes, edges


def to_json(v):
    """Serialize FalkorDB Node/Edge/Path values into plain JSON dicts."""
    t = type(v).__name__
    if t == "Node":
        return {"kind": "node", "labels": list(v.labels or []), "id": v.id,
                "props": dict(v.properties or {})}
    if t == "Edge":
        def _ep(x):
            if x is None:
                return None
            return x if isinstance(x, int) else getattr(x, "id", None)
        return {"kind": "edge", "type": v.relation, "id": v.id,
                "src": _ep(v.src_node), "dst": _ep(v.dest_node),
                "props": dict(v.properties or {})}
    if t == "Path":
        nodes, edges = _path_parts(v)
        return {"kind": "path",
                "nodes": [to_json(n) for n in nodes],
                "edges": [to_json(e) for e in edges]}
    if isinstance(v, (list, tuple)):
        return [to_json(x) for x in v]
    if isinstance(v, dict):
        return {k: to_json(x) for k, x in v.items()}
    return v


def _run_raw(cypher: str, params: dict | None):
    """Execute one Cypher statement; map driver errors to clean HTTP errors."""
    g = get_db().select_graph(GRAPH)
    started = time.time()
    try:
        result = g.query(cypher, params or {})
    except TimeoutError:
        raise HTTPException(504, f"Query timed out after {SOCKET_TIMEOUT:.0f}s")
    except Exception as e:  # noqa: BLE001 — surface FalkorDB errors cleanly
        msg = str(e)
        if "authentication" in msg.lower() or "wrongpass" in msg.lower():
            raise HTTPException(502, "FalkorDB auth failed — check FALKOR_PASSWORD")
        if "refused" in msg.lower() or "connect" in msg.lower():
            raise HTTPException(502, f"Cannot reach FalkorDB at {HOST}:{PORT}")
        raise HTTPException(400, f"Cypher failed: {msg}")
    rows = [dict(zip(cols_of(result), (to_json(c) for c in row)))
            for row in result.result_set]
    return {"cypher": cypher.strip(), "params": params or {}, "rows": rows,
            "ms": round((time.time() - started) * 1000, 1)}


def run_tool(cypher: str, params: dict | None = None) -> dict:
    """Run a read-only agent tool query (write keywords are rejected)."""
    assert_readonly(cypher)
    return _run_raw(cypher, params)


def run_write(cypher: str, params: dict | None = None) -> dict:
    """The sanctioned write path — used only by the freeze action."""
    return _run_raw(cypher, params)


# ------------------------------------------------------- request models

class TraceReq(BaseModel):
    account: str = Field(..., min_length=1, max_length=32,
                         description="Account id, e.g. A-4000")
    depth: int = Field(3, ge=1, le=5, description="Traversal depth (1-5 hops)")


class PageRankReq(BaseModel):
    limit: int = Field(10, ge=1, le=50)


class FreezeReq(BaseModel):
    accounts: list[str] = Field(..., min_length=1, max_length=50)
    reason: str = Field("Suspected fraud ring — agent action", max_length=280)
    investigator: str | None = Field(
        None, max_length=80,
        description="Free-text label, e.g. 'Agent-01'. Not auth — just the case file.")


# ------------------------------------------------------- agent tools

@app.post("/api/tools/trace_hops")
def trace_hops(req: TraceReq):
    """TOOL 1 — multi-hop money trail. The agent suggests a start account;
    the GRAPH decides where the money went."""
    # depth is interpolated (pydantic-validated 1..5) because FalkorDB's
    # OpenCypher needs variable-length bounds as literals, not parameters.
    cypher = f"""
        MATCH path = (start:Account {{id: $acct}})-[:TRANSFERRED*1..{req.depth}]->(end:Account)
        RETURN path LIMIT 25
    """
    out = run_tool(cypher, {"acct": req.account.strip()})
    if not out["rows"]:
        raise HTTPException(404, f"No transfers found from {req.account}")
    return {"tool": "trace_hops", **out}


@app.post("/api/tools/find_ring")
def find_ring():
    """TOOL 2 — fraud rings: 4+ accounts sharing ONE device, plus the IPs they
    share. Classic mule-network fingerprint."""
    cypher = """
        MATCH (a:Account)-[:LOGGED_IN_FROM]->(d:Device)
        WITH d, collect(DISTINCT a) AS accts
        WHERE size(accts) >= 4
        UNWIND accts AS a
        MATCH (a)-[:USED_IP]->(ip:IP)
        WITH d, accts, collect(DISTINCT ip.id) AS ips
        RETURN d.id AS device_id,
               ips,
               [x IN accts | x.id] AS account_ids,
               size(accts) AS ring_size
        ORDER BY ring_size DESC
    """
    return {"tool": "find_ring", **run_tool(cypher)}


@app.post("/api/tools/pagerank_hub")
def pagerank_hub(req: PageRankReq):
    """TOOL 3 — PageRank over TRANSFERRED edges. Money-laundering hubs sit at
    the center of mule networks; PageRank finds them without labels."""
    # limit is interpolated (pydantic-validated 1..50) because FalkorDB's
    # OpenCypher needs LIMIT as a literal, not a parameter.
    cypher = f"""
        CALL algo.pageRank('Account', 'TRANSFERRED')
        YIELD node, score
        RETURN node.id AS account_id, score AS score,
               node.frozen AS frozen, node.risk AS risk
        ORDER BY score DESC
        LIMIT {req.limit}
    """
    return {"tool": "pagerank_hub", **run_tool(cypher)}


# ------------------------------------------------------- agent action

@app.post("/api/actions/freeze")
def freeze(req: FreezeReq):
    """ACTION — the agent ACTS on its findings: freezes the accounts and writes
    a (:Case)-[:TARGETS]->(:Account) case file into the graph. This is the only
    endpoint allowed to mutate the graph."""
    # clean the id list: strip whitespace, drop empties, dedupe (order kept)
    ids = list(dict.fromkeys(a.strip() for a in req.accounts))
    ids = [a for a in ids if a]
    if not ids:
        raise HTTPException(400, "No valid account ids supplied.")
    case_id = f"CASE-{int(time.time())}-{randint(100, 999)}"
    cypher = """
        MATCH (a:Account) WHERE a.id IN $ids AND NOT coalesce(a.frozen, false)
        SET a.frozen = true
        WITH collect(a) AS frozen
        CREATE (c:Case {id: $case_id, created: timestamp(),
                        reason: $reason, investigator: $investigator})
        WITH c, frozen
        UNWIND frozen AS fa
        CREATE (c)-[:TARGETS]->(fa)
        RETURN $case_id AS case_id,
               [x IN frozen | x.id] AS frozen_now,
               size(frozen) AS frozen_count
    """
    out = run_write(cypher, {
        "ids": ids,
        "case_id": case_id,
        "reason": req.reason,
        "investigator": req.investigator or "Agent-01",
    })
    return {"action": "freeze", **out}


# ------------------------------------------------------- helpers

@app.get("/api/graph/stats")
def stats():
    cypher = """
        MATCH (p:Person) WITH count(p) AS persons
        MATCH (a:Account) WITH persons, count(a) AS accounts
        MATCH ()-[t:TRANSFERRED]->()
          WITH persons, accounts, count(t) AS transfers
        OPTIONAL MATCH (f:Account) WHERE coalesce(f.frozen, false)
          WITH persons, accounts, transfers, count(f) AS frozen
        OPTIONAL MATCH (c:Case)
        RETURN persons, accounts, transfers, frozen, count(c) AS cases
    """
    return run_tool(cypher)


@app.get("/api/health")
def health():
    try:
        get_db().select_graph(GRAPH).query("RETURN 1 AS ok")
        return {"status": "ok", "graph": GRAPH, "host": HOST}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"FalkorDB unreachable: {e}")


# ------------------------------------------------------- UI

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
def ui():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()
