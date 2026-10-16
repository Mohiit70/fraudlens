"""
FraudLens v2 seed script — builds a synthetic fraud-investigation graph.

Data model:
    (Person)-[:OWNS]->(Account)
    (Account)-[:LOGGED_IN_FROM]->(Device)
    (Account)-[:USED_IP]->(IP)
    (Account)-[:TRANSFERRED {amount, txn}]->(Account)

Seeds 60 people / 80 legit accounts / ~600 legit transfers, then plants
3 fraud rings: each ring = 5 accounts sharing ONE device + ONE IP, cycling
money round-robin in structuring-sized amounts (just under the 10,000
reporting threshold).

Idempotent: uses UNWIND ... MERGE, safe to re-run.

Usage:
    python seed.py            # seed the 'fraudlens' graph
    python seed.py --verify   # print node counts + detected rings after seeding

Env (same as app.py): FALKOR_HOST, FALKOR_PORT, FALKOR_GRAPH,
FALKOR_USER, FALKOR_PASSWORD (empty = local Docker, no auth).
"""
import os
import random
import sys
from falkordb import FalkorDB

GRAPH = os.getenv("FALKOR_GRAPH", "fraudlens")
HOST = os.getenv("FALKOR_HOST", "localhost")
PORT = int(os.getenv("FALKOR_PORT", "6379"))
USER = os.getenv("FALKOR_USER", "default")
PASSWORD = os.getenv("FALKOR_PASSWORD", "")

random.seed(42)

FIRST = ["Aarav", "Priya", "Rohan", "Sneha", "Vikram", "Ananya", "Karan", "Divya",
         "Arjun", "Meera", "Aditya", "Kavya", "Rahul", "Ishita", "Varun", "Nisha",
         "Sahil", "Riya", "Manav", "Tara"]
LAST = ["Sharma", "Verma", "Gupta", "Iyer", "Khan", "Patel", "Reddy", "Nair",
        "Singh", "Das", "Kulkarni", "Joshi", "Mehta", "Chopra", "Bose", "Menon"]
DEVICES = ["Redmi Note 13", "Samsung A54", "iPhone 13", "Realme 11 Pro", "Pixel 8",
           "OnePlus 11R", "Moto G85", "Vivo V30"]
COUNTRIES = ["IN", "IN", "IN", "IN", "AE", "SG", "US", "GB"]


def connect():
    kw = {"host": HOST, "port": PORT,
          "socket_connect_timeout": 10, "socket_timeout": 60}
    if PASSWORD:
        kw["username"] = USER
        kw["password"] = PASSWORD
    return FalkorDB(**kw)


def build_legit():
    """Background population: 60 people, 80 accounts, 600 random transfers."""
    persons, accounts, _, _, transfers, owns, logins, ipuses = ([] for _ in range(8))

    for i in range(60):
        pid = f"P-{1000 + i}"
        persons.append({"id": pid,
                        "name": f"{random.choice(FIRST)} {random.choice(LAST)}"})

    dev_list = [{"id": f"D-{2000 + i}", "model": random.choice(DEVICES)}
                for i in range(40)]
    ip_list = [{"id": f"IP-203.0.113.{i}", "country": random.choice(COUNTRIES)}
               for i in range(30)]

    acct_ids = []
    for i in range(80):
        aid = f"A-{3000 + i}"
        owner = persons[i % 60]["id"]
        accounts.append({"id": aid,
                         "balance": round(random.uniform(500, 200000), 2),
                         "frozen": False, "risk": 0})
        owns.append({"p": owner, "a": aid})
        # realistic: each device / IP cluster is shared by only 2-3 accounts,
        # so the planted rings (5 accounts, 1 device) stand out
        logins.append({"a": aid, "d": dev_list[(i // 2) % 40]["id"]})
        ipuses.append({"a": aid, "ip": ip_list[(i // 3) % 30]["id"]})
        acct_ids.append(aid)

    txn = 0
    for _ in range(600):
        src, dst = random.sample(acct_ids, 2)
        txn += 1
        transfers.append({"src": src, "dst": dst,
                          "amount": round(random.uniform(50, 50000), 2),
                          "txn": f"TXN-{9000 + txn}"})
    return persons, accounts, dev_list, ip_list, transfers, owns, logins, ipuses


def build_rings(ring_no, size, base):
    """One planted fraud ring: `size` mule accounts, ONE shared device + ONE
    shared IP, money cycling round-robin in just-under-threshold amounts."""
    device = {"id": f"D-RING{ring_no}", "model": "Infinix Hot 40i"}
    ip = {"id": f"IP-198.51.100.{ring_no}", "country": "KY"}
    persons, accounts, transfers, owns, logins, ipuses = ([] for _ in range(6))
    acct_ids = []
    for j in range(size):
        pid = f"P-RING{ring_no}-{j}"
        aid = f"A-{base + j}"
        persons.append({"id": pid, "name": f"Mule {ring_no}-{j}"})
        accounts.append({"id": aid, "balance": 0.0, "frozen": False, "risk": 95})
        owns.append({"p": pid, "a": aid})
        logins.append({"a": aid, "d": device["id"]})
        ipuses.append({"a": aid, "ip": ip["id"]})
        acct_ids.append(aid)
    # circular flow, 4 rounds, structuring-sized amounts (under 10,000)
    txn = 0
    for _ in range(4):
        for j in range(size):
            txn += 1
            transfers.append({"src": acct_ids[j], "dst": acct_ids[(j + 1) % size],
                              "amount": round(random.uniform(9000, 9900), 2),
                              "txn": f"TXN-R{ring_no}-{txn}"})
    return persons, accounts, [device], [ip], transfers, owns, logins, ipuses


def seed():
    db = connect()
    g = db.select_graph(GRAPH)

    P, A, D, IP, T, O, L, U = build_legit()
    for n in (1, 2, 3):
        r = build_rings(n, 5, 4000 + (n - 1) * 10)
        for acc, new in zip((P, A, D, IP, T, O, L, U), r):
            acc.extend(new)

    # idempotent merges — safe to re-run
    g.query("UNWIND $rows AS p MERGE (:Person {id: p.id, name: p.name})",
            {"rows": P})
    # set account props on merge-create only (re-runs keep existing values,
    # so a re-seed never un-freezes accounts)
    g.query("""
        UNWIND $rows AS r
        MERGE (a:Account {id: r.id})
        ON CREATE SET a.balance = r.balance, a.frozen = r.frozen, a.risk = r.risk
    """, {"rows": A})
    g.query("UNWIND $rows AS d MERGE (:Device {id: d.id, model: d.model})",
            {"rows": D})
    g.query("UNWIND $rows AS i MERGE (:IP {id: i.id, country: i.country})",
            {"rows": IP})

    g.query("""
        UNWIND $rows AS r
        MATCH (p:Person {id: r.p}), (a:Account {id: r.a})
        MERGE (p)-[:OWNS]->(a)
    """, {"rows": O})
    g.query("""
        UNWIND $rows AS r
        MATCH (a:Account {id: r.a}), (d:Device {id: r.d})
        MERGE (a)-[:LOGGED_IN_FROM]->(d)
    """, {"rows": L})
    g.query("""
        UNWIND $rows AS r
        MATCH (a:Account {id: r.a}), (i:IP {id: r.ip})
        MERGE (a)-[:USED_IP]->(i)
    """, {"rows": U})
    # transfers keyed on txn id so re-runs don't duplicate edges;
    # batched in chunks so cloud seeding stays fast (one round-trip per 250)
    for i in range(0, len(T), 250):
        g.query("""
            UNWIND $rows AS r
            MATCH (s:Account {id: r.src}), (d:Account {id: r.dst})
            MERGE (s)-[t:TRANSFERRED {txn: r.txn}]->(d)
            ON CREATE SET t.amount = r.amount
        """, {"rows": T[i:i + 250]})

    auth = "with password auth" if PASSWORD else "no auth (local)"
    print(f"Seeded graph '{GRAPH}' on {HOST}:{PORT} ({auth})")


def verify():
    db = connect()
    g = db.select_graph(GRAPH)
    for label in ("Person", "Account", "Device", "IP"):
        n = g.query(f"MATCH (n:{label}) RETURN count(n) AS c").result_set[0][0]
        print(f"  {label}: {n}")
    n = g.query("MATCH ()-[t:TRANSFERRED]->() RETURN count(t) AS c"
                ).result_set[0][0]
    print(f"  TRANSFERRED: {n}")
    rings = g.query("""
        MATCH (a:Account)-[:LOGGED_IN_FROM]->(d:Device)
        WITH d, collect(DISTINCT a) AS accts
        WHERE size(accts) >= 4
        RETURN d.id AS device, size(accts) AS ring_size
        ORDER BY ring_size DESC
    """).result_set
    print(f"  planted rings detected (shared device, >=4 accounts): {len(rings)}/3")
    for row in rings:
        print(f"    {row[0]} -> {row[1]} accounts")


if __name__ == "__main__":
    seed()
    if "--verify" in sys.argv:
        verify()
