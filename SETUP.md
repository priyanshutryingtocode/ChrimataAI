# AI Finance Controller — Local Setup Instructions

## 1. Project Goal

Build an AI Finance Controller for the Razorpay Buildathon Track 04.

The system will reconcile a batch of 50+ synthetic financial records across multiple sources, measure its reconciliation performance, and produce an honest list of unresolved exceptions.

### Core flow

```text
Orders / Invoices
        +
Payments
        +
Settlements
        +
Refunds
        |
        v
Data Normalization
        |
        v
Deterministic Reconciliation Engine
        |
        +----------------------+
        |                      |
        v                      v
   Reconciled              Exceptions
        |                      |
        +----------+-----------+
                   |
                   v
             Evaluation
                   |
                   v
            AI Controller
       (explanations + Q&A)
                   |
                   v
              Dashboard
```

The LLM must NOT be responsible for the core financial calculations, match-rate calculation, or ground-truth evaluation. Those must be deterministic and auditable.

---

# 2. Recommended Stack

Use:

- **Python 3.11+**
- **FastAPI** — backend API
- **Uvicorn** — ASGI server
- **Pandas / NumPy** — data processing
- **Pydantic** — schemas and validation
- **PostgreSQL / Supabase** — persistent storage
- **python-dotenv** — environment variables
- **LLM provider** — add the provider SDK only when implementing the AI layer
- **React + Vite** — frontend
- **Tailwind CSS** — frontend styling

Do not introduce LangChain/LangGraph unless there is a clear need. Start with a simple service-oriented architecture and add agent orchestration only if it provides value.

---

# 3. Initial Repository Structure

Create the following structure:

```text
ai-finance-controller/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   │
│   │   ├── api/
│   │   │   ├── routes.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   └── database.py
│   │   │
│   │   ├── reconciliation/
│   │   │   ├── matcher.py
│   │   │   ├── rules.py
│   │   │   ├── exceptions.py
│   │   │   └── metrics.py
│   │   │
│   │   ├── agent/
│   │   │   ├── controller.py
│   │   │   ├── prompts.py
│   │   │   └── tools.py
│   │   │
│   │   └── models/
│   │       └── transaction.py
│   │
│   ├── data/
│   │   ├── generated/
│   │   └── ground_truth/
│   │
│   ├── tests/
│   │   ├── test_matching.py
│   │   └── test_metrics.py
│   │
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   └── ...
│
├── scripts/
│   └── generate_data.py
│
├── .gitignore
└── README.md
```

Keep the reconciliation engine independent from the LLM.

---

# 4. Python Environment

From the project root:

```bash
python -m venv backend/venv
```

Windows:

```bash
backend\venv\Scripts\activate
```

macOS/Linux:

```bash
source backend/venv/bin/activate
```

Install dependencies:

```bash
pip install -r backend/requirements.txt
```

---

# 5. Environment Variables

Create:

```text
backend/.env
```

Use `.env.example` as the template.

Initial variables:

```env
APP_ENV=development

DATABASE_URL=

LLM_API_KEY=
LLM_MODEL=

FRONTEND_URL=http://localhost:5173
```

Do not commit `.env`.

Never hard-code API keys in source code.

---

# 6. Backend Bootstrap

Create `backend/app/main.py` with a minimal FastAPI application.

Required endpoints initially:

```text
GET /              -> service information
GET /health        -> health check
```

Run from the `backend` directory:

```bash
uvicorn app.main:app --reload
```

Expected API:

```text
http://127.0.0.1:8000
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

---

# 7. Synthetic Dataset

The project must be based on synthetic data with known ground truth.

Generate at least:

- 100 transactions for development
- 500+ transactions for stress testing

Create four primary sources:

### Orders / Invoices

Suggested fields:

```text
order_id
customer_id
customer_name
order_amount
currency
order_date
```

### Payments

Suggested fields:

```text
payment_id
order_id
customer_id
amount
currency
payment_date
payment_status
```

### Settlements

Suggested fields:

```text
settlement_id
payment_id
settlement_date
gross_amount
processing_fee
tax
net_amount
currency
```

### Refunds

Suggested fields:

```text
refund_id
payment_id
refund_amount
refund_date
refund_status
```

The exact schema can evolve, but IDs and financial amounts must be explicit and traceable.

---

# 8. Ground Truth

The synthetic-data generator must also produce a ground-truth dataset.

For every transaction, record the actual intended relationship and injected anomaly.

Example:

```text
transaction_id
expected_status
exception_type
expected_settlement
actual_settlement
expected_variance
source_records
```

Possible exception types:

```text
NONE
MISSING_SETTLEMENT
AMOUNT_MISMATCH
DUPLICATE_TRANSACTION
FEE_MISMATCH
TAX_MISMATCH
REFUND_NOT_SETTLED
DATE_MISMATCH
UNKNOWN_TRANSACTION
```

Ground truth must never be exposed to the reconciliation engine during normal evaluation.

It exists only for testing and scoring.

---

# 9. Controlled Anomaly Injection

The data generator should intentionally create realistic problems.

For a 100-record dataset, start with something similar to:

```text
70  clean transactions
10  amount mismatches
5   missing settlements
5   duplicates
5   tax/fee mismatches
5   refund-related exceptions
```

The exact distribution can be adjusted.

The generator must be deterministic when given a random seed:

```bash
python scripts/generate_data.py --records 100 --seed 42
```

This makes evaluation reproducible.

---

# 10. Reconciliation Engine

Implement reconciliation WITHOUT an LLM first.

The engine should follow roughly this order:

## Step 1 — Normalize

Normalize:

- IDs
- dates
- currencies
- decimal amounts
- customer names where necessary
- whitespace/casing

Do not use floating-point arithmetic for financial comparisons where avoidable. Use `Decimal` for monetary calculations.

## Step 2 — Candidate matching

Use deterministic identifiers first:

```text
payment_id
order_id
invoice_id
```

If identifiers are missing or inconsistent, use secondary matching signals:

```text
customer
amount
date
currency
```

## Step 3 — Verify financial consistency

For a settlement:

```text
expected_net =
    gross_amount
    - processing_fee
    - tax
    - valid_refunds
```

Compare the expected value with the actual settlement.

Use an explicit monetary tolerance rather than arbitrary fuzzy matching.

## Step 4 — Detect duplicates

Detect:

- duplicate payment IDs
- duplicate settlement IDs
- repeated references
- multiple settlements that appear to represent one transaction

## Step 5 — Classify exceptions

Every unresolved transaction must receive an explicit exception type.

Do not silently discard records.

---

# 11. Reconciliation Result Schema

Each processed transaction should produce a structured result similar to:

```json
{
  "transaction_id": "PAY001",
  "status": "MATCHED",
  "confidence": 1.0,
  "expected_amount": 5000.00,
  "actual_amount": 4820.00,
  "fee": 150.00,
  "tax": 30.00,
  "variance": 0.00,
  "exception_type": null,
  "reason": "Settlement equals payment amount after fee and tax."
}
```

For an exception:

```json
{
  "transaction_id": "PAY002",
  "status": "EXCEPTION",
  "confidence": 1.0,
  "expected_amount": 5000.00,
  "actual_amount": 4700.00,
  "fee": 150.00,
  "tax": 30.00,
  "variance": 120.00,
  "exception_type": "AMOUNT_MISMATCH",
  "reason": "₹120 remains unexplained after known deductions."
}
```

Keep the machine-readable fields separate from natural-language explanations.

---

# 12. Evaluation

This is a core requirement of the buildathon.

Calculate at minimum:

### Throughput

```text
records processed / second
```

### Match rate

```text
successfully reconciled records / total records
```

### Matching precision

```text
correct matches / all predicted matches
```

### Exception recall

```text
correctly detected exceptions / actual exceptions
```

### False-match rate

```text
incorrectly matched records / all matched records
```

Also report:

```text
total records
matched records
unresolved records
total expected amount
total reconciled amount
total unresolved amount
processing time
```

Do not cherry-pick successful transactions.

Always run evaluation across the entire batch.

---

# 13. AI Controller

Only add the LLM after the deterministic reconciliation engine and evaluation system work.

The AI layer should primarily handle:

### Exception explanation

Input structured reconciliation data and explain why a record was not reconciled.

### Financial Q&A

Examples:

```text
How many transactions are unresolved?

What is the total unresolved amount?

What are the top three exception types?

Which transaction has the largest unexplained variance?

Why was TXN-1042 not reconciled?

How much money is currently reconciled?

What percentage of transactions were matched?
```

### Recommendations

For example:

```text
Verify gateway settlement fees for TXN-1042.
```

The LLM must use structured reconciliation results rather than independently recomputing financial values.

---

# 14. AI Safety / Reliability Rules

The controller must:

1. Never invent transaction records.
2. Never invent financial amounts.
3. Never claim an exception is resolved unless the reconciliation engine marked it resolved.
4. Use tool/data results as the source of truth.
5. Clearly distinguish:
   - confirmed facts
   - calculated values
   - probable explanations
   - recommendations
6. Return structured output wherever possible.
7. Have deterministic fallback behavior if the LLM fails.

If the LLM API is unavailable, the core reconciliation and dashboard must still work.

---

# 15. API Design

Initial backend endpoints can be:

```text
GET  /health

POST /api/batches/upload
POST /api/batches/{batch_id}/reconcile

GET  /api/batches/{batch_id}
GET  /api/batches/{batch_id}/metrics
GET  /api/batches/{batch_id}/exceptions

POST /api/controller/query
```

The exact API can evolve during implementation.

---

# 16. Frontend

The dashboard should prioritize the judging criteria.

Main view:

```text
AI FINANCE CONTROLLER

Records Processed      Matched       Exceptions
      150                137             13

Match Rate: 91.33%

Amount Processed:      ₹18,42,650
Amount Reconciled:     ₹17,91,420
Amount Unresolved:       ₹51,230
```

Then show:

- reconciliation table
- exception table
- exception details
- processing time
- throughput
- evaluation metrics
- AI Controller chat

The UI should make the result understandable within a few seconds.

---

# 17. Exception Explorer

For every exception, show:

```text
Transaction ID
Exception type
Expected amount
Actual amount
Variance
Related records
Reason
Confidence
Recommended action
```

Example:

```text
TXN-1042

AMOUNT_MISMATCH

Expected settlement: ₹9,764
Actual settlement:   ₹9,500
Variance:              ₹264

Known deductions:
Fee: ₹200
Tax: ₹36

Unexplained: ₹28

Recommendation:
Verify additional settlement deductions.
```

---

# 18. Testing

Write unit tests for:

- exact matching
- missing settlements
- amount mismatch
- fee calculations
- tax calculations
- duplicates
- refunds
- date tolerance
- exception classification
- evaluation metrics

Every known anomaly type should have test coverage.

Also run a full integration test:

```text
Generate dataset
        ↓
Reconcile
        ↓
Evaluate against ground truth
        ↓
Produce metrics
```

---

# 19. Development Principles

Follow these rules throughout the project:

### Rule 1

**Deterministic financial logic first.**

### Rule 2

**LLM second.**

### Rule 3

**Ground truth is mandatory.**

### Rule 4

**Every unresolved record must be visible.**

### Rule 5

**Never hide failures to improve the match rate.**

### Rule 6

**Use structured data between components.**

### Rule 7

**Keep the system runnable without the LLM.**

### Rule 8

**Prefer simple architecture over unnecessary agent complexity.**

### Rule 9

**Use `Decimal` for monetary calculations.**

### Rule 10

**Make experiments reproducible with fixed random seeds.**

---

# 20. Initial Implementation Order

Implement in this exact order:

```text
1. Repository + Python environment
2. FastAPI health endpoint
3. Synthetic data generator
4. Ground-truth generator
5. Data normalization
6. Deterministic reconciliation engine
7. Exception classification
8. Evaluation/metrics engine
9. Tests
10. Database integration
11. AI Controller
12. Backend APIs
13. Frontend dashboard
14. Exception explorer
15. AI chat
16. End-to-end demo
17. Stress testing on 500+ records
18. Final evaluation report
```

Do not start by building the chatbot or dashboard.

The reconciliation engine and evaluation system are the core product.

---

# 21. Definition of Done for the First Milestone

The first milestone is complete when this command works:

```bash
python scripts/generate_data.py --records 100 --seed 42
```

followed by a reconciliation command/API that produces something like:

```text
RECONCILIATION COMPLETE

Records processed:       100
Matched:                  91
Exceptions:                9

Match rate:             91.00%
Exception recall:       94.44%
False match rate:        1.10%

Processing time:        0.42 sec
Throughput:            238 records/sec

Reconciled amount:     ₹X
Unresolved amount:     ₹Y
```

And, critically:

```text
EXCEPTIONS

1. TXN-1042  AMOUNT_MISMATCH
2. TXN-1051  MISSING_SETTLEMENT
3. TXN-1068  DUPLICATE_TRANSACTION
...
```

The numbers must come from the actual generated batch and ground truth, not hard-coded demo values.

---

# 22. Do Not Overbuild Initially

For the first working version, do NOT implement:

- multi-agent orchestration
- vector databases
- RAG
- complex memory
- autonomous database modifications
- automatic financial actions
- production authentication
- elaborate animations

First prove:

```text
DATA → RECONCILIATION → METRICS → EXCEPTIONS
```

Then add:

```text
→ AI EXPLANATION → AI Q&A → POLISHED UI
```

That is the correct development priority for this buildathon.
