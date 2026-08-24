from __future__ import annotations

from pathlib import Path

from app.core.config import DATA_DIR

BATCH_DATA_ROOT = DATA_DIR / "batches"


def batch_dir(batch_id: str) -> Path:
    return BATCH_DATA_ROOT / batch_id


def generated_dir(batch_id: str) -> Path:
    return batch_dir(batch_id) / "generated"


def ground_truth_file(batch_id: str) -> Path:
    return batch_dir(batch_id) / "ground_truth" / "ground_truth.csv"
