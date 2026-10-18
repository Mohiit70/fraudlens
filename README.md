# 🔎 FraudLens

### Graph-powered fraud investigation agent that traces money, hunts fraud rings, and takes action.

**FraudLens turns suspicious transactions into an explainable investigation in seconds.**

**🔗 Live Demo:** [Open FraudLens](https://fraudlens-y5ba.onrender.com/)

---

## 🚨 The Problem

Modern financial fraud rarely happens through a single account.

A mule network can involve dozens of accounts, shared devices, shared IP addresses, and chains of small transfers designed to avoid detection.

The challenge isn't simply detecting a suspicious transaction.

The real questions are:

Where did the money go? Who is connected? Who controls the network? And what should an investigator do next?

Traditional fraud dashboards mainly generate alerts.

**Investigators still have to manually connect the dots.**

---

# 💡 The Solution

**FraudLens is a graph-powered investigation agent.**

Give it a suspicious account such as:

```text
A-4000
```

FraudLens automatically:

### Trace

Follows money across multi-hop transaction paths.

**25 money trails** can be discovered in seconds.

### Hunt

Finds coordinated fraud rings through shared device and IP fingerprints.

**3 fraud rings** are detected in the seeded investigation dataset.

### Rank

Uses PageRank to identify high-centrality accounts that may represent network hubs or kingpins.

**No manually assigned labels required.**

### Freeze

After investigator confirmation, FraudLens can freeze the suspicious account and create a persistent case record in the graph.

> **It doesn't just explain the crime. It provides a path to action.**

---

# 🎥 See FraudLens In Action

### Live Demo

[Open FraudLens](https://fraudlens-y5ba.onrender.com/)

Try:

```text
A-4000
```

Then click **Investigate**.

---

# 🖥️ Product Preview

### Landing Page

<p align="center">
  <img src="docs/landing.png" width="800" alt="FraudLens Landing Page">
</p>

### Trace The Money

<p align="center">
  <img src="docs/trace.png" width="800" alt="FraudLens Money Trace">
</p>

### Detect Fraud Rings

<p align="center">
  <img src="docs/rings.png" width="800" alt="FraudLens Fraud Ring Detection">
</p>

---

# 🧠 Why Graphs?

Fraud is inherently relational.

A traditional table might show:

```text
Account A → Account B
₹9,000
```

A graph reveals the larger network:

```text
Person
   ↓
Account
   ↓
Account
 ↙     ↘
Device  IP
   ↓     ↓
Other Accounts
      ↓
  Fraud Ring
```

FraudLens models these relationships directly, making **multi-hop investigation fast, visual, and explainable.**

---

# 🏗️ Architecture

<p align="center">
  <img src="docs/architecture.png" width="700" alt="FraudLens Architecture">
</p>

```text
                    ┌──────────────────────┐
                    │     Investigator     │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │      Web Interface   │
                    │       D3.js + JS     │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │       FastAPI        │
                    │   Investigation API  │
                    └──────────┬───────────┘
                               │
                  ┌────────────┴────────────┐
                  ▼                         ▼
        ┌─────────────────┐       ┌─────────────────┐
        │    FalkorDB     │       │   PDF Reports   │
        │  Graph Database │       │      jsPDF      │
        └─────────────────┘       └─────────────────┘
```

---

# 🕸️ Data Model

<p align="center">
  <img src="docs/datamodel.png" width="700" alt="FraudLens Data Model">
</p>

FraudLens represents financial activity as a connected graph.

| Node | Relationship |
|---|---|
| Person | `OWNS → Account` |
| Account | `TRANSFERRED → Account` |
| Account | `USES_DEVICE → Device` |
| Account | `USES_IP → IP` |
| Case | `FROZE → Account` |

### Seeded Investigation Dataset

- **75** persons
- **95** accounts
- **660** transfers
- **3** fraud rings
- **15** mule accounts
- Structuring transactions between **₹9,000–₹9,900**

---

# 🧰 Investigation Tools

| Tool | Purpose | Graph Operation |
|---|---|---|
| `trace_hops` | Trace multi-hop money movement | `TRANSFERRED*1..3` |
| `find_ring` | Detect shared device/IP networks | `USES_DEVICE / USES_IP` |
| `pagerank_hub` | Identify network hubs | PageRank |
| `freeze` | Take investigation action | Creates freeze + case record |

Every investigation operation is backed by an actual graph query.

---

# ⚡ The Investigation Loop

```text
        SUSPICIOUS ACCOUNT
                 │
                 ▼
               TRACE
                 │
                 ▼
        FIND CONNECTIONS
                 │
                 ▼
          DETECT FRAUD RING
                 │
                 ▼
            RANK HUBS
                 │
                 ▼
         INVESTIGATOR REVIEW
                 │
                 ▼
              FREEZE
                 │
                 ▼
          CREATE CASE
```

FraudLens transforms a raw fraud alert into an **actionable investigation workflow.**

---

# 🔐 Safety & Auditability

Financial investigation systems need controlled actions.

FraudLens separates **analysis** from **action**.

### Read-only investigation tools

The tracing, ring detection, and ranking operations are read-only.

They cannot modify the graph.

### Controlled action

`freeze` is the dedicated write operation.

When confirmed, it:

1. Marks the account as frozen.
2. Creates a `Case` node.
3. Links the case to the affected account.
4. Preserves the investigation in the graph.

### Explainable Queries

The Cypher query behind each investigation operation can be displayed to the investigator.

**No hidden database mutations.**

---

# 🏆 What Makes FraudLens Different?

Most fraud systems stop at:

> **"This transaction looks suspicious."**

FraudLens goes further:

> **"Here is how the money moved, here are the connected accounts, here is the suspicious network hub, and here is the action an investigator can take."**

### From Alert → Investigation → Action

```text
ALERT
  ↓
TRACE
  ↓
UNDERSTAND
  ↓
FIND THE RING
  ↓
RANK HUBS
  ↓
REVIEW
  ↓
FREEZE
```

---

# 🛠️ Tech Stack

### Frontend

- Vanilla JavaScript
- D3.js
- Responsive UI
- Interactive force-directed graphs

### Backend

- Python
- FastAPI

### Graph

- FalkorDB
- Cypher
- PageRank

### Reporting

- jsPDF

### Deployment

- Render

---

# 🚀 Quick Start

## Requirements

- Python 3.11+
- FalkorDB instance

FalkorDB Cloud can be used for development.

### 1. Clone

```bash
git clone https://github.com/Mohiit70/fraudlens.git
cd fraudlens
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure FalkorDB

```bash
export FALKOR_HOST="your-instance.falkordb.cloud"
export FALKOR_PORT="6379"
export FALKOR_USER="falkordb"
export FALKOR_PASSWORD="your-password"
```

### 4. Seed the Graph

```bash
python seed.py --verify
```

The seed operation is idempotent and safe to run again.

### 5. Start FraudLens

```bash
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Open:

```text
http://localhost:8000
```

Enter:

```text
A-4000
```

and click **Investigate**.

---

# ☁️ Deploy To Render

### Build Command

```bash
pip install -r requirements.txt
```

### Start Command

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

### Environment Variables

```text
FALKOR_HOST
FALKOR_PORT
FALKOR_USER
FALKOR_PASSWORD
```

---

# 🔮 Future Potential

FraudLens can evolve into a broader financial-crime investigation platform with:

- Real-time transaction ingestion
- Streaming fraud detection
- Continuous network monitoring
- Investigator collaboration
- Advanced risk scoring
- Additional graph algorithms
- Historical case analytics
- Automated regulatory reporting
- Larger financial-network datasets

---


---
