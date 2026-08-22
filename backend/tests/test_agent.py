from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import helpers
from app.agent.controller import extract_transaction_ids, run_controller_query
from app.core.formatting import format_inr


@pytest.fixture()
def client(tmp_path):
    test_client, session_factory = helpers.make_test_client(tmp_path)
    test_client.session_factory = session_factory
    yield test_client
    helpers.release_test_client()


@pytest.fixture()
def reconciled_batch(client):
    return helpers.upload_and_reconcile(client, records=40, seed=42)


def query(client, batch_id: str, question: str) -> dict:
    response = client.post("/api/controller/query", json={"batch_id": batch_id, "question": question})
    assert response.status_code == 200, response.text
    return response.json()


def test_extract_transaction_ids():
    question = "Why was PAY-00012 not reconciled? Also check setl-00051 and PAY-00012 again."
    assert extract_transaction_ids(question) == ["PAY-00012", "SETL-00051"]
    assert extract_transaction_ids("nothing here") == []


def test_query_unknown_batch_404(client):
    response = client.post(
        "/api/controller/query", json={"batch_id": "missing", "question": "How many?"}
    )
    assert response.status_code == 404


def test_query_unreconciled_batch_409(client):
    files = helpers.make_dataset_files(records=20, seed=3)
    files.pop("ground_truth")
    batch = helpers.upload_batch(client, files)
    response = client.post(
        "/api/controller/query", json={"batch_id": batch["id"], "question": "How many?"}
    )
    assert response.status_code == 409


def test_unresolved_count_question(client, reconciled_batch):
    answer = query(client, reconciled_batch["id"], "How many transactions are unresolved?")
    metrics = client.get(f"/api/batches/{reconciled_batch['id']}/metrics").json()

    assert answer["source"] == "deterministic_fallback"
    assert answer["kind"] == "FACTUAL"
    assert str(metrics["exception_records"]) in answer["answer"]
    assert answer["key_figures"]["Match rate"] == f"{metrics['match_rate'] * 100:.2f}%"


def test_unresolved_amount_question(client, reconciled_batch):
    answer = query(client, reconciled_batch["id"], "What is the total unresolved amount?")
    metrics = client.get(f"/api/batches/{reconciled_batch['id']}/metrics").json()

    expected = format_inr(Decimal(str(round(metrics["unresolved_amount"], 2))))
    assert expected in answer["key_figures"]["Unresolved amount"] or f"{expected}" in answer["answer"]


def test_reconciled_amount_question(client, reconciled_batch):
    answer = query(
        client, reconciled_batch["id"], "How much money is currently reconciled?"
    )
    metrics = client.get(f"/api/batches/{reconciled_batch['id']}/metrics").json()

    expected = format_inr(Decimal(str(round(metrics["reconciled_amount"], 2))))
    assert expected in answer["key_figures"]["Reconciled amount"]
    assert answer["kind"] == "CALCULATED"


def test_match_rate_percentage_question(client, reconciled_batch):
    answer = query(client, reconciled_batch["id"], "What percentage of transactions were matched?")
    metrics = client.get(f"/api/batches/{reconciled_batch['id']}/metrics").json()

    assert f"{metrics['match_rate'] * 100:.2f}%" in answer["answer"]


def test_top_exception_types_question(client, reconciled_batch):
    answer = query(client, reconciled_batch["id"], "What are the top three exception types?")

    assert answer["kind"] == "FACTUAL"
    assert len(answer["key_figures"]) >= 1
    assert any("AMOUNT_MISMATCH" in name for name in answer["key_figures"])


def test_largest_variance_question_cites_top_exception(client, reconciled_batch):
    top = client.get(f"/api/batches/{reconciled_batch['id']}/exceptions", params={"limit": 1}).json()["items"][0]
    answer = query(
        client, reconciled_batch["id"], "Which transaction has the largest unexplained variance?"
    )

    assert top["transaction_id"] in answer["cited_transactions"]
    assert format_inr(Decimal(str(abs(top["variance"])))).lstrip("-") in (
        answer["key_figures"].get("Variance", "") + answer["answer"]
    )


def test_explain_specific_exception(client, reconciled_batch):
    exceptions = client.get(
        f"/api/batches/{reconciled_batch['id']}/exceptions",
        params={"exception_type": "AMOUNT_MISMATCH", "limit": 1},
    ).json()["items"]
    target = exceptions[0]

    answer = query(
        client,
        reconciled_batch["id"],
        f"Why was {target['transaction_id']} not reconciled?",
    )

    assert answer["kind"] == "EXPLANATION"
    assert answer["cited_transactions"] == [target["transaction_id"]]
    assert target["reason"].split(".")[0] in answer["confirmed_facts"][1]
    assert answer["recommendations"], "recommendation should be surfaced"


def test_unknown_transaction_not_found(client, reconciled_batch):
    answer = query(client, reconciled_batch["id"], "Why was TXN-99999 not reconciled?")

    assert answer["kind"] == "NOT_FOUND"


def test_fallback_survives_llm_failure(client, reconciled_batch, monkeypatch):
    from app.agent import controller

    def boom():
        raise RuntimeError("simulated Gemini outage")

    monkeypatch.setattr(controller, "_get_gemini_client", boom)
    answer = query(client, reconciled_batch["id"], "How many transactions are unresolved?")

    assert answer["source"] == "deterministic_fallback"
    assert answer["kind"] == "FACTUAL"
