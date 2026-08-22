from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.batch import Batch, TransactionResultRow

DEFAULT_TOP_EXCEPTIONS = 5


@dataclass(frozen=True)
class BatchFacts:
    batch_id: str
    batch_name: str
    status: str
    total_records: int
    matched_records: int
    exception_records: int
    match_rate: float
    total_expected_amount: Decimal
    reconciled_amount: Decimal
    unresolved_amount: Decimal
    elapsed_seconds: float
    throughput_per_second: float
    evaluated_against_ground_truth: bool
    matching_precision: float | None = None
    exception_recall: float | None = None
    false_match_rate: float | None = None


@dataclass(frozen=True)
class TransactionDetail:
    transaction_id: str
    status: str
    confidence: float
    expected_amount: Decimal | None
    actual_amount: Decimal | None
    fee: Decimal | None
    tax: Decimal | None
    variance: Decimal | None
    exception_type: str
    reason: str
    recommendation: str
    match_method: str
    related_records: list[str] = field(default_factory=list)


def get_batch_facts(db: Session, batch_id: str) -> BatchFacts | None:
    batch = db.get(Batch, batch_id)
    if batch is None or batch.status != "RECONCILED":
        return None

    rows = db.scalars(
        select(TransactionResultRow).where(TransactionResultRow.batch_id == batch_id)
    ).all()
    total = len(rows)
    matched_rows = [row for row in rows if row.status == "MATCHED"]
    total_expected = sum((row.expected_amount or Decimal("0") for row in rows), Decimal("0"))
    reconciled = sum((row.expected_amount or Decimal("0") for row in matched_rows), Decimal("0"))
    elapsed = max(batch.elapsed_seconds or 0.0, 1e-9)

    facts = BatchFacts(
        batch_id=batch_id,
        batch_name=batch.name,
        status=batch.status,
        total_records=total,
        matched_records=len(matched_rows),
        exception_records=total - len(matched_rows),
        match_rate=len(matched_rows) / total if total else 0.0,
        total_expected_amount=total_expected,
        reconciled_amount=reconciled,
        unresolved_amount=total_expected - reconciled,
        elapsed_seconds=batch.elapsed_seconds or 0.0,
        throughput_per_second=total / elapsed,
        evaluated_against_ground_truth=False,
    )

    if batch.evaluation_json:
        stored = json.loads(batch.evaluation_json)
        facts = BatchFacts(
            **{
                **facts.__dict__,
                "matching_precision": stored.get("matching_precision"),
                "exception_recall": stored.get("exception_recall"),
                "false_match_rate": stored.get("false_match_rate"),
                "evaluated_against_ground_truth": True,
            }
        )
    return facts


def get_exception_type_distribution(db: Session, batch_id: str) -> dict[str, int]:
    counts = db.execute(
        select(TransactionResultRow.exception_type, func.count())
        .where(TransactionResultRow.batch_id == batch_id)
        .where(TransactionResultRow.status == "EXCEPTION")
        .group_by(TransactionResultRow.exception_type)
        .order_by(func.count().desc())
    ).all()
    return {exception_type: count for exception_type, count in counts}


def list_top_exceptions(
    db: Session,
    batch_id: str,
    limit: int = DEFAULT_TOP_EXCEPTIONS,
) -> list[TransactionDetail]:
    rows = db.scalars(
        select(TransactionResultRow)
        .where(TransactionResultRow.batch_id == batch_id)
        .where(TransactionResultRow.status == "EXCEPTION")
        .order_by(TransactionResultRow.variance_abs_paise.desc(), TransactionResultRow.transaction_id.asc())
        .limit(limit)
    ).all()
    return [_row_to_detail(row) for row in rows]


def find_transaction(db: Session, batch_id: str, transaction_id: str) -> TransactionDetail | None:
    normalized = transaction_id.strip().upper()
    row = db.scalar(
        select(TransactionResultRow).where(
            TransactionResultRow.batch_id == batch_id,
            TransactionResultRow.transaction_id == normalized,
        )
    )
    return _row_to_detail(row) if row else None


def _row_to_detail(row: TransactionResultRow) -> TransactionDetail:
    return TransactionDetail(
        transaction_id=row.transaction_id,
        status=row.status,
        confidence=row.confidence,
        expected_amount=row.expected_amount,
        actual_amount=row.actual_amount,
        fee=row.fee,
        tax=row.tax,
        variance=row.variance,
        exception_type=row.exception_type,
        reason=row.reason,
        recommendation=row.recommendation,
        match_method=row.match_method,
        related_records=[item for item in row.related_records.split("|") if item],
    )
