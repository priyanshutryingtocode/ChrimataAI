from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import generate_data
import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db, SessionLocal
from app.main import app

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app.core import database

    test_db_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    test_engine = database.create_engine(test_db_url, future=True)
    database.Base.metadata.create_all(bind=test_engine)
    testing_session = database.sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False, future=True)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_dataset_files(records: int = 40, seed: int = 42):
    dataset = generate_data.generate_dataset(records, seed)
    files = {
        "orders": ("orders.csv", _to_csv(generate_data.ORDER_FIELDS, dataset.orders), "text/csv"),
        "payments": ("payments.csv", _to_csv(generate_data.PAYMENT_FIELDS, dataset.payments), "text/csv"),
        "settlements": ("settlements.csv", _to_csv(generate_data.SETTLEMENT_FIELDS, dataset.settlements), "text/csv"),
        "refunds": ("refunds.csv", _to_csv(generate_data.REFUND_FIELDS, dataset.refunds), "text/csv"),
        "ground_truth": (
            "ground_truth.csv",
            _to_csv(generate_data.GROUND_TRUTH_FIELDS, dataset.ground_truth),
            "text/csv",
        ),
    }
    return files


def _to_csv(fields: list[str], rows: list[dict[str, str]]) -> bytes:
    lines = [",".join(fields)]
    for row in rows:
        lines.append(",".join(row[field] for field in fields))
    return ("\n".join(lines) + "\n").encode("utf-8")


def upload_batch(client: TestClient, files) -> dict:
    response = client.post(
        "/api/batches/upload",
        data={"name": "test batch"},
        files={key: value for key, value in files.items()},
    )
    assert response.status_code == 200, response.text
    return response.json()


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

    exceptions = client.get(
        f"/api/batches/{batch['id']}/exceptions", params={"limit": 5}
    ).json()
    injected = sum(1 for row in files["ground_truth"][1].decode().splitlines()[1:] if ",EXCEPTION," in row)
    assert exceptions["total"] == injected
    assert len(exceptions["items"]) <= 5

    filtered = client.get(
        f"/api/batches/{batch['id']}/exceptions", params={"exception_type": "AMOUNT_MISMATCH"}
    ).json()
    assert all(item["exception_type"] == "AMOUNT_MISMATCH" for item in filtered["items"])

    bad_type = client.get(
        f"/api/batches/{batch['id']}/exceptions", params={"exception_type": "NOT_A_TYPE"}
    )
    assert bad_type.status_code == 422


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
