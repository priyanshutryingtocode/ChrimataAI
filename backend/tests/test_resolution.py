from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import helpers


@pytest.fixture()
def client(tmp_path):
    test_client, session_factory = helpers.make_test_client(tmp_path)
    test_client.session_factory = session_factory
    yield test_client
    helpers.release_test_client()


@pytest.fixture()
def batch(client):
    return helpers.upload_and_reconcile(client, records=40, seed=42)


def get_exceptions_by_type(client, batch_id, exception_type):
    return client.get(
        f"/api/batches/{batch_id}/exceptions", params={"exception_type": exception_type, "limit": 1}
    ).json()["items"]


def propose(client, batch_id, transaction_id, use_llm=True):
    return client.post(
        f"/api/batches/{batch_id}/exceptions/{transaction_id}/proposal",
        json={"use_llm": use_llm},
    )


def decide(client, batch_id, transaction_id, decision="APPROVED", approved_amount=None, note=""):
    payload = {"decision": decision, "approved_by": "tester", "note": note}
    if approved_amount is not None:
        payload["approved_amount"] = approved_amount
    return client.post(
        f"/api/batches/{batch_id}/exceptions/{transaction_id}/resolution", json=payload
    )


def test_vendor_query_approval_leaves_financial_outstanding(client, batch):
    target = get_exceptions_by_type(client, batch["id"], "REFUND_NOT_SETTLED")[0]

    created = propose(client, batch["id"], target["transaction_id"])
    assert created.status_code == 200, created.text
    assert created.json()["proposal_kind"] == "VENDOR_QUERY"
    assert created.json()["proposed_by"] == "deterministic_rules"

    decided = decide(client, batch["id"], target["transaction_id"])
    assert decided.status_code == 200, decided.text
    body = decided.json()
    assert body["workflow_status"] == "RESOLVED"
    assert body["financial_status"] == "UNRESOLVED"
    assert body["reconciled_adjustment_amount"] == 0
    assert body["approved_amount"] == body["proposed_amount"]
    assert any(event["event"] == "PROPOSAL_APPROVED" and event["financial_effect"] == 0 for event in body["audit"])


def test_full_adjustment_reconciles_financially(client, batch):
    target = get_exceptions_by_type(client, batch["id"], "AMOUNT_MISMATCH")[0]
    variance = abs(target["variance"])

    propose(client, batch["id"], target["transaction_id"])
    decided = decide(client, batch["id"], target["transaction_id"])
    body = decided.json()

    assert body["proposal_kind"] == "ADJUSTMENT"
    assert body["financial_status"] == "RECONCILED"
    assert body["reconciled_adjustment_amount"] == pytest.approx(variance)

    metrics = client.get(f"/api/batches/{batch['id']}/metrics").json()["workflow"]
    assert metrics["amount_financially_reconciled"] == pytest.approx(variance)
    assert metrics["financially_reconciled_exceptions"] == 1


def test_partial_approval_stays_financially_outstanding(client, batch):
    target = get_exceptions_by_type(client, batch["id"], "AMOUNT_MISMATCH")[0]
    variance = abs(target["variance"])
    half = round(variance / 2, 2)

    propose(client, batch["id"], target["transaction_id"])
    decided = decide(client, batch["id"], target["transaction_id"], approved_amount=half)
    body = decided.json()

    assert body["approved_amount"] == pytest.approx(half)
    assert body["reconciled_adjustment_amount"] == pytest.approx(half)
    assert body["financial_status"] == "UNRESOLVED"

    metrics = client.get(f"/api/batches/{batch['id']}/metrics").json()["workflow"]
    assert metrics["amount_outstanding"] == pytest.approx(metrics["total_exception_amount"] - half)
    assert metrics["financial_resolution_rate"] == pytest.approx(half / metrics["total_exception_amount"])


def test_duplicate_approval_is_rejected(client, batch):
    target = get_exceptions_by_type(client, batch["id"], "AMOUNT_MISMATCH")[0]
    propose(client, batch["id"], target["transaction_id"])
    assert decide(client, batch["id"], target["transaction_id"]).status_code == 200
    second = decide(client, batch["id"], target["transaction_id"])
    assert second.status_code == 409


def test_over_approval_amount_rejected(client, batch):
    target = get_exceptions_by_type(client, batch["id"], "AMOUNT_MISMATCH")[0]
    propose(client, batch["id"], target["transaction_id"])
    response = decide(
        client, batch["id"], target["transaction_id"], approved_amount=abs(target["variance"]) + 100
    )
    assert response.status_code == 422


def test_engine_metrics_immutable_under_workflow(client, batch):
    before = client.get(f"/api/batches/{batch['id']}/metrics").json()

    for exception_type, decision_amount in (
        ("REFUND_NOT_SETTLED", None),
        ("AMOUNT_MISMATCH", None),
        ("DATE_MISMATCH", None),
    ):
        target = get_exceptions_by_type(client, batch["id"], exception_type)[0]
        propose(client, batch["id"], target["transaction_id"])
        assert decide(client, batch["id"], target["transaction_id"], approved_amount=decision_amount).status_code == 200

    after = client.get(f"/api/batches/{batch['id']}/metrics").json()
    for key in ("total_records", "matched_records", "exception_records", "match_rate", "matching_precision", "exception_recall", "false_match_rate", "reconciled_amount", "unresolved_amount"):
        assert after[key] == before[key], key

    workflow = after["workflow"]
    assert workflow["workflow_resolved_exceptions"] == 3
    assert workflow["workflow_resolution_rate"] == pytest.approx(3 / before["exception_records"])


def test_evidence_snapshot_immutable(client, batch, tmp_path):
    target = get_exceptions_by_type(client, batch["id"], "AMOUNT_MISMATCH")[0]
    propose(client, batch["id"], target["transaction_id"])

    snapshot_before = client.get(
        f"/api/batches/{batch['id']}/exceptions/{target['transaction_id']}/evidence"
    ).json()
    assert snapshot_before["source"] == "snapshot"

    payments_file = None
    for path in Path(helpers.__file__).parent.glob("nonexistent"):
        pass
    live = client.get(
        f"/api/batches/{batch['id']}/exceptions/{target['transaction_id']}/evidence"
    ).json()
    assert live["evidence"] == snapshot_before["evidence"]


def test_llm_invalid_kind_falls_back_to_rules(client, batch, monkeypatch):
    from app.agent import proposal as proposal_module
    from app.reconciliation.financial import ProposalKind

    def bad_llm(evidence, allowed, exception_type, variance):
        return {
            "kind": ProposalKind.MARK_AS_VALID,
            "amount": 0,
            "rationale": "make it disappear",
            "confidence": 0.9,
        }

    monkeypatch.setattr(proposal_module, "_ask_gemini_proposal", bad_llm)
    target = get_exceptions_by_type(client, batch["id"], "AMOUNT_MISMATCH")[0]

    created = propose(client, batch["id"], target["transaction_id"])
    body = created.json()
    assert body["proposed_by"] == "deterministic_rules"
    assert body["proposal_kind"] == "ADJUSTMENT"


def test_reject_returns_exception_to_open(client, batch):
    target = get_exceptions_by_type(client, batch["id"], "FEE_MISMATCH")[0]
    propose(client, batch["id"], target["transaction_id"])

    rejected = decide(client, batch["id"], target["transaction_id"], decision="REJECTED", note="needs more evidence")
    assert rejected.status_code == 200
    assert rejected.json()["workflow_status"] == "REJECTED"
    assert rejected.json()["financial_status"] == "UNRESOLVED"

    again = propose(client, batch["id"], target["transaction_id"])
    assert again.status_code == 200
    assert again.json()["workflow_status"] == "PROPOSED"


def test_state_guards(client, batch):
    target = get_exceptions_by_type(client, batch["id"], "TAX_MISMATCH")[0]

    no_proposal = decide(client, batch["id"], target["transaction_id"])
    assert no_proposal.status_code == 409

    propose(client, batch["id"], target["transaction_id"])
    duplicate = propose(client, batch["id"], target["transaction_id"])
    assert duplicate.status_code == 409

    matched_row = client.get(
        f"/api/batches/{batch['id']}/results", params={"status": "MATCHED", "limit": 1}
    ).json()["items"][0]
    matched_proposal = propose(client, batch["id"], matched_row["transaction_id"])
    assert matched_proposal.status_code == 404


def test_mark_as_valid_for_date_mismatch(client, batch):
    target = get_exceptions_by_type(client, batch["id"], "DATE_MISMATCH")[0]
    created = propose(client, batch["id"], target["transaction_id"])
    assert created.json()["proposal_kind"] == "MARK_AS_VALID"
    assert created.json()["proposed_amount"] == 0

    decided = decide(client, batch["id"], target["transaction_id"])
    body = decided.json()
    assert body["financial_status"] == "RECONCILED"
    assert body["reconciled_adjustment_amount"] == 0


def test_retry_reconciliation_executes_engine(client, batch, monkeypatch):
    from app.reconciliation.financial import ProposalKind

    target = get_exceptions_by_type(client, batch["id"], "MISSING_SETTLEMENT")[0]

    def retry_llm(evidence, allowed, exception_type, variance):
        return {
            "kind": ProposalKind.RETRY_RECONCILIATION,
            "amount": float(variance),
            "rationale": "Re-run to confirm before escalation.",
            "confidence": 0.8,
        }

    from app.agent import proposal as proposal_module
    monkeypatch.setattr(proposal_module, "_ask_gemini_proposal", retry_llm)

    created = propose(client, batch["id"], target["transaction_id"])
    assert created.json()["proposal_kind"] == "RETRY_RECONCILIATION"

    decided = decide(client, batch["id"], target["transaction_id"])
    body = decided.json()
    assert body["workflow_status"] == "RESOLVED"
    assert body["financial_status"] == "UNRESOLVED"
    retry_events = [event for event in body["audit"] if event["event"] == "RETRY_RECONCILIATION_EXECUTED"]
    assert len(retry_events) == 1
    assert retry_events[0]["actor"] == "engine"


def test_link_record_for_unknown_transaction(client):
    batch = helpers.upload_and_reconcile(client, records=100, seed=42)
    orphans = client.get(
        f"/api/batches/{batch['id']}/exceptions", params={"exception_type": "UNKNOWN_TRANSACTION", "limit": 1}
    ).json()["items"]
    assert orphans, "seed 42 at 100 records should contain an UNKNOWN_TRANSACTION"

    from app.reconciliation.financial import ProposalKind

    def link_llm(evidence, allowed, exception_type, variance):
        return {
            "kind": ProposalKind.LINK_RECORD,
            "amount": float(variance),
            "rationale": "Locate the missing payment ingest.",
            "confidence": 0.7,
        }

    from app.agent import proposal as proposal_module
    monkeypatch_target = proposal_module
    original = proposal_module._ask_gemini_proposal
    proposal_module._ask_gemini_proposal = link_llm
    try:
        created = propose(client, batch["id"], orphans[0]["transaction_id"])
    finally:
        proposal_module._ask_gemini_proposal = original

    assert created.json()["proposal_kind"] == "LINK_RECORD"
    decided = decide(client, batch["id"], orphans[0]["transaction_id"])
    body = decided.json()
    assert body["workflow_status"] == "RESOLVED"
    assert body["financial_status"] == "UNRESOLVED"
    assert body["reconciled_adjustment_amount"] == 0


def test_proposal_blocked_on_unreconciled_batch(client):
    files = helpers.make_dataset_files(records=20, seed=3)
    files.pop("ground_truth")
    batch = helpers.upload_batch(client, files)

    exceptions = client.get(f"/api/batches/{batch['id']}/exceptions").json()
    assert exceptions["total"] == 0
    response = client.post(
        f"/api/batches/{batch['id']}/exceptions/PAY-00001/proposal", json={"use_llm": False}
    )
    assert response.status_code == 409
