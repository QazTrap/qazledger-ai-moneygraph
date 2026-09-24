# QazLedger AI

AI accounting and financial analysis agent for Kazakhstan businesses.

QazLedger AI analyzes bank statement transactions, classifies accounting operations and prepares unposted draft documents in 1C for accountant review.

For HackAlem AI, the project was extended with **QazLedger MoneyGraph** — an AML transaction-network analysis module.

---

# HackAlem AI — QazLedger MoneyGraph

**Track 02 — Finance**

QazLedger MoneyGraph helps an AML analyst reconstruct the movement of funds through a transaction network, identify important accounts in the chain and prioritize nodes that require additional review.

The project now contains two MoneyGraph modes:

1. **Full AML parquet pipeline** — the reproducible HackAlem analysis pipeline that assigns the six required functional roles, performs clustering and generates the required CSV outputs.
2. **Web demo** — an interactive prototype with a simplified legacy role model, Risk Score and OpenAI-generated explanation.

The full parquet pipeline is deterministic and does not require OpenAI to calculate roles, clusters or priority scores.

---

## Full AML Pipeline

### What it does

The pipeline:

- loads the HackAlem parquet dataset;
- builds a directed transaction graph;
- calculates incoming and outgoing flow metrics;
- calculates PageRank and betweenness centrality;
- assigns one functional role to every node;
- calculates `role_score`;
- performs Louvain community detection;
- assigns `cluster_id`;
- calculates `priority_score`;
- generates explainable evidence for every node;
- creates a ranked Top-20 or larger list;
- exports the required CSV files.

### Input data

The pipeline expects these files locally:

```text
data/
├── edges.parquet
├── nodes.parquet
└── transactions.parquet
```

The dataset is not included in the public repository.

### Supported node roles

The full pipeline assigns one of six roles:

- `consolidator` — receives funds from many sources and concentrates incoming flow;
- `distributor` — sends funds to many recipients;
- `transit` — passes most received funds further through the network;
- `terminal` — retains most incoming funds with limited outgoing activity;
- `coordinator` — structurally important node connecting multiple transaction flows;
- `peripheral` — node without a strongly expressed functional role.

### Explainable role criteria

Role assignment is deterministic.

#### coordinator

A node is considered a coordinator when it:

- has both incoming and outgoing flow;
- has at least 2 incoming and 2 outgoing neighbors;
- has PageRank at or above the 90th percentile;
- has betweenness centrality at or above the 90th percentile.

#### consolidator

A node is considered a consolidator when its incoming degree is at least:

```text
max(3, 90th percentile of in_degree)
```

and it has positive incoming flow.

#### distributor

A node is considered a distributor when its outgoing degree is at least:

```text
max(3, 90th percentile of out_degree)
```

and it has positive outgoing flow.

#### transit

For non-seed nodes, a node can be classified as transit when:

```text
0.80 <= outgoing / incoming <= 1.20
```

with positive incoming and outgoing flow.

#### terminal

For non-seed nodes with `depth < 4`, a node can be classified as terminal when:

```text
outgoing <= 10% of incoming
```

#### peripheral

Nodes that do not match a stronger role are classified as peripheral.

---

## Data-quality safeguards

The pipeline explicitly handles known limitations of the provided graph.

### depth=4 boundary

Nodes at `depth=4` are the boundary of the provided graph.

A node at `depth=4` with no outgoing edges is **not automatically classified as terminal**, because the missing outgoing flow may be caused by the graph extraction boundary.

### Seed nodes

Incoming flow for seed clients can be incomplete.

Therefore seed nodes are **not classified as `terminal` or `transit` using the flow ratio rule**.

### No hardcoded answers

The pipeline does not contain hardcoded GIDs or manually inserted expected results.

Roles, clusters and priorities are calculated from the input data.

---

## Graph metrics

For each node the pipeline calculates:

- `in_degree`;
- `out_degree`;
- `in_sum_kzt`;
- `out_sum_kzt`;
- `flow_ratio`;
- PageRank;
- betweenness centrality;
- normalized graph metrics.

---

## Clustering

The directed graph is projected to a weighted undirected graph for community detection.

Edge weight:

```text
sum_kzt
```

Primary algorithm:

```text
Louvain community detection
```

with deterministic seed:

```text
seed=42
```

Fallback:

```text
Greedy Modularity Communities
```

On the provided HackAlem dataset the pipeline produced:

- **2,248 nodes**;
- **91 clusters**;
- **8 clusters containing more than one seed client**.

---

## Priority Score

Every node receives `priority_score` in the range `0..1`.

The score combines:

- functional role;
- `role_score`;
- incoming and outgoing activity;
- transaction volume;
- PageRank;
- betweenness centrality.

Current formula:

```text
priority_score =
    0.40 * role_bonus
  + 0.30 * role_score
  + 0.15 * activity
  + 0.15 * centrality
```

where:

```text
activity =
    0.30 * in_degree_norm
  + 0.30 * out_degree_norm
  + 0.20 * in_sum_kzt_norm
  + 0.20 * out_sum_kzt_norm
```

and:

```text
centrality =
    0.45 * pagerank_norm
  + 0.55 * betweenness_norm
```

---

## Required outputs

The pipeline creates:

```text
output/
├── nodes_roles.csv
├── clusters.csv
└── top_nodes.csv
```

### nodes_roles.csv

Columns:

```text
gid
role
role_score
cluster_id
priority_score
evidence
```

Verified result:

```text
2248 rows
```

### clusters.csv

Columns:

```text
cluster_id
n_nodes
n_seed
sum_kzt_internal
top_gids
hypothesis
```

Verified result:

```text
91 rows
```

### top_nodes.csv

Columns:

```text
rank
gid
role
priority_score
why
```

Verified result:

```text
20 rows
```

The `--top` argument can request a larger list, but the pipeline always produces at least 20 rows.

---

## Validation results

The pipeline was validated on the provided dataset.

```text
nodes_roles.csv: 2248 rows
clusters.csv: 91 rows
top_nodes.csv: 20 rows
```

Validation checks:

```text
empty evidence: 0
role_score outside 0..1: 0
priority_score outside 0..1: 0
empty cluster_id: 0
```

Role distribution after data-quality safeguards:

```text
terminal        1083
peripheral       767
consolidator     165
distributor      140
transit           47
coordinator       46
```

Seed-node roles:

```text
peripheral      53
distributor     14
coordinator      7
consolidator     7
```

No seed node is classified as `terminal` or `transit`.

At `depth=4`:

```text
peripheral     441
consolidator     3
terminal         0
```

---

## Benchmark

Measured local run:

```text
OS: Windows
Python: 3.14
Nodes: 2,248
Edges: 3,119
Full pipeline runtime: ~3.97 seconds
```

The `< 5 minutes` requirement is satisfied with a large margin.

---

## Run the full pipeline

From the project root:

```bash
py -m pip install -r requirements.txt
py pipeline/pipeline.py --data data --out output --top 20
```

Expected result:

```text
QazLedger MoneyGraph pipeline complete
nodes_roles.csv: 2248 rows
clusters.csv: 91 rows
top_nodes.csv: 20 rows
```

Python dependencies:

```text
pandas>=2.2
pyarrow>=17.0
networkx>=3.3
numpy>=1.26
scipy>=1.18
```

---

## Architecture

```text
HackAlem parquet data
        ↓
Data validation
        ↓
Directed transaction graph
        ↓
Graph metrics
        ↓
PageRank + Betweenness
        ↓
Louvain clustering
        ↓
Functional role detection
        ↓
Role Score
        ↓
Priority Score
        ↓
Explainable evidence
        ↓
CSV outputs
        ↓
AML analyst review
```

The analyst remains the final decision-maker.

---

## Scaling to larger graphs

The current implementation is intentionally simple and reproducible for the provided HackAlem dataset.

For graphs approaching 1,000,000 nodes, the architecture can be scaled by:

- using PyArrow/Parquet partitioning and chunked processing;
- replacing exact betweenness centrality with sampled or approximate betweenness;
- using graph engines such as Networkit, igraph or another optimized graph backend;
- running Louvain/Leiden community detection on a memory-efficient graph representation;
- calculating metrics incrementally where possible;
- persisting intermediate graph metrics instead of recalculating everything on every run.

The current pipeline does not require GPU or cloud infrastructure.

---

# MoneyGraph Web Demo

The repository also contains the original interactive MoneyGraph prototype.

The web demo uses a simplified legacy role model:

- `COLLECTOR`;
- `DISTRIBUTOR`;
- `TRANSIT`;
- `SINK`;
- `NORMAL`.

This legacy model is kept for the interactive demonstration.

The **full parquet pipeline described above uses the six-role HackAlem classification**:

- `consolidator`;
- `distributor`;
- `transit`;
- `terminal`;
- `coordinator`;
- `peripheral`.

## Web Demo Workflow

```text
Transactions
      ↓
Graph Construction
      ↓
Flow Analysis
      ↓
Legacy Role Detection
      ↓
Risk Score
      ↓
Top Risk Ranking
      ↓
OpenAI Explanation
      ↓
AML Analyst Review
```

The legacy Risk Score and legacy node roles are calculated by deterministic application logic.

OpenAI is used only to explain the already calculated web-demo results in human-readable form.

AI does not determine whether an account or person has committed an illegal activity.

## Example

```text
A001 ─┐
A002 ─┼──→ B001 ───→ C001
A003 ─┘
          COLLECTOR
          Risk 66
```

Example values:

```text
B001
Role: COLLECTOR
Risk Score: 66
Incoming: 370000
Outgoing: 340000
Unique Senders: 3
Unique Receivers: 1
Flow Ratio: 0.92
```

## Web interface

The web interface displays:

- transaction input;
- transaction graph;
- node roles;
- Risk Score;
- Top Risk ranking;
- incoming and outgoing amounts;
- AI-generated AML explanation.

![QazLedger MoneyGraph](screenshots/moneygraph.jpg)

---

# MoneyGraph API

### POST /api/moneygraph

Receives an array of transactions and returns the web-demo analysis.

Example request:

```json
{
  "transactions": [
    {
      "from": "A001",
      "to": "B001",
      "amount": 100000,
      "date": "2026-09-20"
    },
    {
      "from": "A002",
      "to": "B001",
      "amount": 150000,
      "date": "2026-09-20"
    },
    {
      "from": "A003",
      "to": "B001",
      "amount": 120000,
      "date": "2026-09-21"
    },
    {
      "from": "B001",
      "to": "C001",
      "amount": 340000,
      "date": "2026-09-21"
    }
  ]
}
```

---

# Original QazLedger AI

## Problem

Accountants spend significant time manually processing bank statements:

- identifying counterparties;
- understanding payment purposes;
- classifying transactions;
- checking internal transfers;
- entering data into 1C;
- avoiding duplicate documents.

This process is repetitive and error-prone.

## Solution

QazLedger AI combines AI analysis with deterministic accounting rules and 1C integration.

The system can:

- import Kaspi Bank statements;
- analyze transaction direction and payment purpose;
- identify counterparties;
- classify accounting operations;
- detect internal transfers between own bank accounts;
- detect Kaspi Pay fees;
- detect Kaspi Bank fees;
- detect sales receipts;
- detect payments to accountable persons;
- return confidence score and explanation;
- allow the accountant to select which transactions should be created;
- create unposted draft documents in 1C;
- prevent duplicate document creation;
- never post accounting documents automatically.

## Accounting Workflow

```text
Bank Statement
      ↓
1C Statement Import
      ↓
QazLedger AI Analysis
      ↓
Transaction Classification
      ↓
Accountant Review
      ↓
Selected Transactions
      ↓
Unposted 1C Draft Documents
      ↓
Manual Verification
      ↓
Posting by Accountant
```

## Human-in-the-loop

QazLedger AI is designed as a human-in-the-loop accounting assistant.

AI does not directly post accounting documents.

The accountant can review:

- transaction date;
- amount;
- counterparty;
- AI decision;
- AI rule;
- confidence score;
- status;
- explanation.

Only transactions explicitly selected by the accountant are sent to the 1C document creation layer.

---

# QazLedger Backend

Technologies:

- Node.js;
- Express;
- OpenAI API;
- JavaScript.

### POST /api/analyze

Receives one structured banking transaction and returns:

- accounting rule;
- operation name;
- transaction direction;
- suggested document;
- confidence score;
- manual review flag;
- explanation;
- suggested comment.

---

# 1C Integration

Integration is implemented for:

**1C: Accounting for Kazakhstan, edition 3.0**

The 1C module:

- imports the bank statement;
- sends transactions for AI analysis;
- displays AI results;
- allows manual approval;
- creates unposted accounting drafts;
- searches existing documents;
- protects against duplicate creation;
- resolves own-bank-account transfers.

## Example Classifications

- `SALE`
- `INTERNAL_TRANSFER`
- `ACCOUNTABLE_PERSON`
- `KASPI_PAY_FEE`
- `KASPI_BANK_FEE`
- `SUPPLIER_PAYMENT`
- `REFUND`
- `TAX_PAYMENT`
- `PAYROLL`
- `MANUAL_REVIEW`

## Internal Transfers

For transfers between the company's own bank accounts, QazLedger AI determines the transfer direction and creates only the required accounting document.

Example:

```text
Alatau City Bank → Kaspi Bank
```

The system creates an unposted outgoing payment order with:

- source bank account;
- destination bank account;
- amount;
- KNP;
- transaction date.

Duplicate internal-transfer documents are not created.

---

# Safety

## Accounting module

- no automatic posting;
- human confirmation before document creation;
- duplicate protection;
- confidence-based review;
- unposted drafts only;
- accountant remains in control.

## MoneyGraph full pipeline

- roles and priority scores are analytical indicators;
- evidence is derived from graph metrics;
- the pipeline does not declare a person or account criminal;
- final assessment remains with the AML analyst.

## MoneyGraph web demo

- Risk Score is an analytical priority indicator;
- OpenAI explains calculated graph patterns;
- AI does not declare an account suspicious or criminal;
- final assessment remains with the AML analyst.

---

# Current Status

Working prototype.

### Accounting workflow

```text
Kaspi Statement
→ AI Analysis
→ Human Approval
→ 1C Draft
→ Duplicate Check
```

Current 1C integration version:

```text
v1.5.0
```

### Full MoneyGraph pipeline

```text
Parquet
→ Graph
→ Metrics
→ Clusters
→ Six Roles
→ Priority Score
→ CSV Outputs
→ Analyst Review
```

### MoneyGraph web demo

```text
Transactions
→ Graph Analysis
→ Legacy Role Detection
→ Risk Score
→ OpenAI Explanation
→ Analyst Review
```

---

# Working Prototype

## AI Transaction Analysis

QazLedger AI analyzes bank statement transactions directly inside 1C and shows the proposed accounting decision, rule, confidence score and explanation.

![QazLedger AI transaction analysis](screenshots/ai-analysis.jpg)

## 1C Draft Creation

After accountant approval, QazLedger AI creates an unposted 1C accounting document.

![QazLedger AI 1C internal transfer](screenshots/internal-transfer.jpg)

## MoneyGraph AML Analysis

The web demo visualizes a transaction network and its legacy Risk Score.

The full Python pipeline performs the reproducible six-role AML analysis and CSV export.

![QazLedger MoneyGraph](screenshots/moneygraph.jpg)

---

# Run the Web Demo

Go to the backend directory:

```bash
cd backend
```

Install dependencies:

```bash
npm install
```

Create a local `.env` file:

```env
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5.6-terra
```

Do not upload `.env` to GitHub.

Start the server:

```bash
npm start
```

Open:

```text
http://localhost:3000
```

Health check:

```text
http://localhost:3000/health
```

Expected result:

```json
{
  "ok": true
}
```

---

# Project Structure

```text
/
├── backend/
│   ├── public/
│   │   └── index.html
│   ├── package.json
│   └── server.js
│
├── pipeline/
│   └── pipeline.py
│
├── 1c/
│   ├── README.md
│   ├── ASIQ_Kaspi_1C_v1.5.0_OWN_TRANSFER_DIRECTION.txt
│   └── ASIQ_Kaspi_QazLedgerAI_CREATE_SELECTED_FULL.txt
│
├── screenshots/
│   ├── ai-analysis.jpg
│   ├── internal-transfer.jpg
│   └── moneygraph.jpg
│
├── requirements.txt
├── PIPELINE_README.md
├── .gitignore
└── README.md
```

Local-only folders:

```text
data/
output/
```

Both are ignored by Git.

---

# Reproducibility Summary

Full AML pipeline:

```bash
py -m pip install -r requirements.txt
py pipeline/pipeline.py --data data --out output --top 20
```

Verified:

```text
2248 node roles
91 clusters
20 ranked top nodes
8 multi-seed clusters
~3.97 second runtime
```

No hardcoded GIDs are used.

The final AML assessment remains with the human analyst.
