# AI Finance Controller

Deterministic payments reconciliation with an LLM-grounded assistant. Built for the
Razorpay Buildathon Track 04.

The system reconciles batches of synthetic financial records across four sources
(orders, payments, settlements, refunds), measures its own performance against known
ground truth, and surfaces every unresolved exception. An AI controller (Gemini)
explains exceptions and answers questions — but only from stored reconciliation
results, never by recomputing money.

```
Orders + Payments + Settlements + Refunds
        |
        v
Data Normalization            (Decimal money, ISO dates)
        |
        v
Deterministic Reconciliation Engine   <- no LLM anywhere near this box
        |                    ID match -> financial verify -> duplicates ->
        |                    exception classification
        v
Evaluation vs Ground Truth    (precision, recall, false-match rate)
        |
        v
AI Controller                 (explanations + Q&A over structured results,
        |                      deterministic fallback if the LLM is down)
        v
Dashboard                     (React + Vite + Tailwind)
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
