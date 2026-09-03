# Chrimata AI - Finance Controller

Deterministic payments reconciliation with an LLM-grounded assistant. Built for the
Razorpay Buildathon Track 04.

The system reconciles batches of synthetic financial records across four sources
(orders, payments, settlements, refunds), measures its own performance against known
ground truth, and surfaces every unresolved exception. An AI controller (Gemini)
explains exceptions and answers questions — but only from stored reconciliation
results, never by recomputing money.

```
                      [Razorpay API → Adapter → SourceData] ─┐
                                                             ↓
Orders + Payments + Settlements + Refunds → Data Normalization → Deterministic Reconciliation Engine
         (CSV upload)              (Decimal money, ISO dates)   (ID match → financial verify → duplicates → exception classification)
                                                                 |
                                                                 v
                                                          Evaluation vs Ground Truth → AI Controller (grounded) → Dashboard
```

## Quickstart

### Backend

```bash
cd backend
python -m venv venv
venv/Scripts/activate          # Git Bash on Windows (source venv/bin/activate on macOS/Linux)
pip install -r requirements.txt

# generate synthetic data with ground truth (fixed seed = reproducible)
python ../scripts/generate_data.py --records 100 --seed 42

# run reconciliation + evaluation report in the terminal
python ../scripts/reconcile.py

# start the API
python -m uvicorn app.main:app --reload     # http://127.0.0.1:8000/docs
```

### Frontend

```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

Optional: set `LLM_API_KEY` (and optionally `LLM_MODEL`) in `backend/.env` to enable
live Gemini answers in the controller chat. Without a key everything still works via
the deterministic fallback — the chat shows which source answered.

## CSV Upload Format

Upload via **Dashboard → Upload dataset** or `POST /api/batches/upload` (multipart `orders`, `payments`, `settlements`, `refunds`, `ground_truth`).

| File field | Header — must be exactly this (lowercased check) | Required |
|---|---|---|
| `payments` | `payment_id,order_id,customer_id,amount,currency,payment_date,payment_status` | **Yes** |
| `settlements` | `settlement_id,payment_id,settlement_date,gross_amount,processing_fee,tax,net_amount,currency` | **Yes** |
| `orders` | `order_id,customer_id,customer_name,order_amount,currency,order_date` | No |
| `refunds` | `refund_id,payment_id,refund_amount,refund_date,refund_status` | No |
| `ground_truth` | `transaction_id,expected_status,exception_type,expected_settlement,actual_settlement,expected_variance,source_records` | No — without it `GET /metrics` returns `evaluated_against_ground_truth: false` |

**Formatting rules** (validated in `reconciliation/normalize.py`): UTF-8, header row required, blank rows ignored. Amounts as `Decimal` like `47549.00` (commas/`₹` are stripped); dates as `YYYY-MM-DD`; currency as `INR` (uppercased, defaults to `INR`); IDs trimmed + uppercased.

**Minimal examples — copy, save as `.csv`, and upload:**

```csv
# payments.csv
payment_id,order_id,customer_id,amount,currency,payment_date,payment_status
PAY-00001,ORD-00001,CUST-001,47549.00,INR,2026-06-12,captured
```

```csv
# settlements.csv
settlement_id,payment_id,settlement_date,gross_amount,processing_fee,tax,net_amount,currency
SETL-00001,PAY-00001,2026-06-13,47549.00,950.98,171.18,46426.84,INR
```

```csv
# orders.csv
order_id,customer_id,customer_name,order_amount,currency,order_date
ORD-00001,CUST-001,Aarav Sharma,47549.00,INR,2026-06-11
```

```csv
# refunds.csv
refund_id,payment_id,refund_amount,refund_date,refund_status
REF-00001,PAY-00010,850.00,2026-06-13,processed
```

Working templates with 100 seeded records live at `backend/data/generated/*.csv` and `backend/data/ground_truth/ground_truth.csv` — generate your own with `python scripts/generate_data.py --records 100 --seed 42`.

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/batches/upload` | Upload orders/payments/settlements/refunds CSVs (+ optional ground truth) |
| `POST /api/batches/{id}/reconcile` | Run the engine and persist results |
| `GET  /api/batches/{id}` | Batch metadata and counts |
| `GET  /api/batches/{id}/metrics` | Match rate, precision/recall, amounts, throughput |
| `GET  /api/batches/{id}/results?status=&limit=&offset=` | Paginated reconciliation rows |
| `GET  /api/batches/{id}/exceptions?exception_type=` | Exception rows, variance-ordered |
| `POST /api/controller/query` | Ask about a batch; structured answer with citations |
| `GET /health` | DB-aware health — `{"status":"ok","db":"up"}` or `503 {"db":"down"}` |

## Real-Data Adapters (stub)

`backend/app/adapters/` provides a no-op bridge for live data without touching the deterministic core:

* `adapters/base.py` — `RealDataAdapter.fetch(params) -> SourceData`
* `adapters/razorpay.py` — `RazorpayAdapter` mapping `Order/Payment/Settlement/Refund → app.models.transaction.*` (Decimal money, `normalize_id`, `parse_money` invariants preserved). Requires `RAZORPAY_KEY_ID` + `RAZORPAY_KEY_SECRET` in `backend/.env`; without them `validate_credentials() is False` and `fetch()` raises `NotImplementedError` — the CSV path remains the source of truth.

## Evaluation metrics

- **Match rate** — successfully reconciled records / total records
- **Matching precision** — correct matches / all predicted matches
- **Exception recall** — correctly detected exceptions (exact subtype) / actual injected exceptions
- **False-match rate** — incorrectly matched / all matched records
- **Throughput** — records processed per second

Ground truth is generated alongside the data with fixed seeds, is never exposed to the
engine during reconciliation, and is used only for scoring.

## Stress testing and final report

```bash
python scripts/stress_test.py                       # size x seed matrix, honesty gate on exit code
python scripts/final_report.py                      # consolidated report -> backend/data/reports/
```

The honesty gate fails the run if any configuration drops below 100% precision or
produces false matches or false alarms.

## Design principles honored

1. Deterministic financial logic first; LLM strictly second.
2. Ground truth is mandatory and isolated from the engine.
3. Every unresolved record is visible; failures are never hidden to inflate match rate.
4. Structured data between components; machine-readable fields separated from prose.
5. The system is fully functional without the LLM.
6. `Decimal` for all monetary arithmetic; no floating point in financial comparisons.
7. Fixed random seeds make every experiment reproducible.

## Tests

```bash
backend/venv/Scripts/python -m pytest backend/tests -q      # Windows/Git Bash
backend/venv/bin/python -m pytest backend/tests -q          # macOS/Linux
```

Covers: every injected anomaly type, matching rules, metric math, the full API flow
(upload -> reconcile -> metrics -> exceptions -> controller query), and an end-to-end
generate -> reconcile -> evaluate pipeline.
