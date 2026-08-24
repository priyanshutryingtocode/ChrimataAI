from __future__ import annotations

import sys
from pathlib import Path

import generate_data
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import helpers


@pytest.fixture()
def client(tmp_path):
    test_client, _ = helpers.make_test_client(tmp_path)
    yield test_client
    helpers.release_test_client()


def upload_batch(client, files) -> dict:
    return helpers.upload_batch(client, files)


def make_dataset_files(records: int = 40, seed: int = 42):
    return helpers.make_dataset_files(records, seed)


def test_full_batch_flow(client):
    files = make_dataset_files(records=40, seed=42)
    allocation = generate_data.allocate_counts(40)
    batch = upload_batch(client, files)

    assert batch["status"] == "UPLOADED"
    assert batch["orders_count"] == 40
    assert batch["payments_count"] == 40 + allocation["DUPLICATE_TRANSACTION"] - allocation["UNKNOWN_TRANSACTION"]
    assert batch["settlements_count"] == 40 - allocation["MISSING_SETTLEMENT"]
    assert batch["has_ground_truth"] is True

    listed = client.get("/api/batches").json()
    assert any(item["id"] == batch["id"] for item in listed)

    metrics_before = client.get(f"/api/batches/{batch['id']}/metrics")
    assert metrics_before.status_code == 409

    reconciled = client.post(f"/api/batches/{batch['id']}/reconcile")
    assert reconciled.status_code == 200, reconciled.text
    assert reconciled.json()["status"] == "RECONCILED"

    detail = client.get(f"/api/batches/{batch['id']}").json()
    assert detail["status"] == "RECONCILED"

    metrics = client.get(f"/api/batches/{batch['id']}/metrics").json()
    assert metrics["evaluated_against_ground_truth"] is True
    assert metrics["total_records"] == 40
    assert metrics["matching_precision"] == pytest.approx(1.0)
    assert metrics["exception_recall"] == pytest.approx(1.0)
    assert metrics["false_match_rate"] == pytest.approx(0.0)

    exceptions = client.get(f"/api/batches/{batch['id']}/exceptions", params={"limit": 5}).json()
    injected = sum(1 for row in files["ground_truth"][1].decode().splitlines()[1:] if ",EXCEPTION," in row)
    assert exceptions["total"] == injected
    assert len(exceptions["items"]) <= 5

    filtered = client.get(
        f"/api/batches/{batch['id']}/exceptions", params={"exception_type": "AMOUNT_MISMATCH"}
    ).json()
    assert all(item["exception_type"] == "AMOUNT_MISMATCH" for item in filtered["items"])

    bad_type = client.get(f"/api/batches/{batch['id']}/exceptions", params={"exception_type": "NOT_A_TYPE"})
    assert bad_type.status_code == 422


def test_results_endpoint_filters_and_pagination(client):
    batch = helpers.upload_and_reconcile(client, records=40, seed=42)
    metrics = client.get(f"/api/batches/{batch['id']}/metrics").json()

    all_rows = client.get(f"/api/batches/{batch['id']}/results", params={"limit": 500}).json()
    assert all_rows["total"] == metrics["total_records"]
    matched_sample = next(item for item in all_rows["items"] if item["status"] == "MATCHED")
    assert "net_expected" in matched_sample
    assert matched_sample["net_expected"] == pytest.approx(matched_sample["actual_amount"])
    assert matched_sample["expected_amount"] - matched_sample["net_expected"] > 0

    matched_rows = client.get(f"/api/batches/{batch['id']}/results", params={"status": "MATCHED", "limit": 500}).json()
    assert matched_rows["total"] == metrics["matched_records"]
    assert all(item["status"] == "MATCHED" for item in matched_rows["items"])

    exception_rows = client.get(
        f"/api/batches/{batch['id']}/results", params={"status": "EXCEPTION", "limit": 500}
    ).json()
    assert exception_rows["total"] == metrics["exception_records"]
    assert exception_rows["total"] > 0

    paged = client.get(f"/api/batches/{batch['id']}/results", params={"limit": 5, "offset": 0}).json()
    assert len(paged["items"]) == 5
    paged_two = client.get(f"/api/batches/{batch['id']}/results", params={"limit": 5, "offset": 5}).json()
    first_ids = {item["transaction_id"] for item in paged["items"]}
    second_ids = {item["transaction_id"] for item in paged_two["items"]}
    assert not first_ids & second_ids

    bad_status = client.get(f"/api/batches/{batch['id']}/results", params={"status": "WEIRD"})
    assert bad_status.status_code == 422


def test_upload_rejects_bad_headers(client):
    payments = ("payments.csv", b"wrong,header\n1,2\n", "text/csv")
    settlements = ("settlements.csv", b"x\ny\n", "text/csv")
    response = client.post("/api/batches/upload", files={"payments": payments, "settlements": settlements})
    assert response.status_code == 422


def test_reconcile_unknown_batch_returns_404(client):
    assert client.post("/api/batches/deadbeef/reconcile").status_code == 404


def test_metrics_without_ground_truth(client):
    files = make_dataset_files(records=20, seed=7)
    files.pop("ground_truth")
    batch = upload_batch(client, files)
    client.post(f"/api/batches/{batch['id']}/reconcile")

    metrics = client.get(f"/api/batches/{batch['id']}/metrics").json()
    assert metrics["evaluated_against_ground_truth"] is False
    assert metrics["matching_precision"] is None
    assert metrics["total_records"] > 0
