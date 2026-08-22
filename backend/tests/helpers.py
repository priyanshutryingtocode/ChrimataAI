from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
for path in (str(BACKEND_DIR), str(ROOT_DIR / "scripts")):
    if path not in sys.path:
        sys.path.insert(0, path)

import generate_data
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app


def make_test_client(tmp_path):
    from app.core import database

    test_engine = database.create_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}", future=True)
    database.Base.metadata.create_all(bind=test_engine)
    testing_session = database.sessionmaker(
        bind=test_engine, autoflush=False, expire_on_commit=False, future=True
    )

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), testing_session


def release_test_client() -> None:
    app.dependency_overrides.clear()


def to_csv(fields: list[str], rows: list[dict[str, str]]) -> bytes:
    lines = [",".join(fields)]
    for row in rows:
        lines.append(",".join(row[field] for field in fields))
    return ("\n".join(lines) + "\n").encode("utf-8")


def make_dataset_files(records: int = 40, seed: int = 42, include_ground_truth: bool = True) -> dict:
    dataset = generate_data.generate_dataset(records, seed)
    files = {
        "orders": ("orders.csv", to_csv(generate_data.ORDER_FIELDS, dataset.orders), "text/csv"),
        "payments": ("payments.csv", to_csv(generate_data.PAYMENT_FIELDS, dataset.payments), "text/csv"),
        "settlements": (
            "settlements.csv",
            to_csv(generate_data.SETTLEMENT_FIELDS, dataset.settlements),
            "text/csv",
        ),
        "refunds": ("refunds.csv", to_csv(generate_data.REFUND_FIELDS, dataset.refunds), "text/csv"),
    }
    if include_ground_truth:
        files["ground_truth"] = (
            "ground_truth.csv",
            to_csv(generate_data.GROUND_TRUTH_FIELDS, dataset.ground_truth),
            "text/csv",
        )
    return files


def upload_batch(client: TestClient, files: dict, name: str = "test batch") -> dict:
    response = client.post("/api/batches/upload", data={"name": name}, files=files)
    assert response.status_code == 200, response.text
    return response.json()


def upload_and_reconcile(client: TestClient, records: int = 40, seed: int = 42) -> dict:
    batch = upload_batch(client, make_dataset_files(records, seed))
    reconciled = client.post(f"/api/batches/{batch['id']}/reconcile")
    assert reconciled.status_code == 200, reconciled.text
    return reconciled.json()
