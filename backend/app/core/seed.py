from __future__ import annotations

import json
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = ROOT_DIR / "scripts"
BACKEND_DIR = ROOT_DIR / "backend"
for p in (str(BACKEND_DIR), str(SCRIPTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import generate_data
from app.core.database import SessionLocal
from app.models.batch import Batch, TransactionResultRow, utc_now
from app.reconciliation.engine import run_reconciliation
from app.reconciliation.metrics import evaluate
from app.models.transaction import Order, Payment, Refund, Settlement, SourceData


def _parse_decimal(value: str) -> Decimal:
    return Decimal(value) if value else Decimal("0")


def _parse_date(value: str) -> date | None:
    return date.fromisoformat(value) if value else None


def seed_demo_if_empty() -> str | None:
    db = SessionLocal()
    try:
        if db.query(Batch).count() > 0:
            return None

        dataset = generate_data.generate_dataset(100, 42)

        orders: list[Order] = []
        for row in dataset.orders:
            orders.append(
                Order(
                    order_id=row["order_id"],
                    customer_id=row["customer_id"],
                    customer_name=row["customer_name"],
                    order_amount=Decimal(row["order_amount"]),
                    currency=row["currency"],
                    order_date=date.fromisoformat(row["order_date"]),
                )
            )

        payments: list[Payment] = []
        for row in dataset.payments:
            payments.append(
                Payment(
                    payment_id=row["payment_id"],
                    order_id=row["order_id"],
                    customer_id=row["customer_id"],
                    amount=Decimal(row["amount"]),
                    currency=row["currency"],
                    payment_date=date.fromisoformat(row["payment_date"]),
                    payment_status=row["payment_status"],
                )
            )

        settlements: list[Settlement] = []
        for row in dataset.settlements:
            settlements.append(
                Settlement(
                    settlement_id=row["settlement_id"],
                    payment_id=row["payment_id"],
                    settlement_date=date.fromisoformat(row["settlement_date"]),
                    gross_amount=Decimal(row["gross_amount"]),
                    processing_fee=Decimal(row["processing_fee"]),
                    tax=Decimal(row["tax"]),
                    net_amount=Decimal(row["net_amount"]),
                    currency=row["currency"],
                )
            )

        refunds: list[Refund] = []
        for row in dataset.refunds:
            refunds.append(
                Refund(
                    refund_id=row["refund_id"],
                    payment_id=row["payment_id"],
                    refund_amount=Decimal(row["refund_amount"]),
                    refund_date=date.fromisoformat(row["refund_date"]),
                    refund_status=row["refund_status"],
                )
            )

        source = SourceData(orders=orders, payments=payments, settlements=settlements, refunds=refunds)
        report = run_reconciliation(source)

        ground_truth_df = pd.DataFrame(dataset.ground_truth)
        evaluation = evaluate(report, ground_truth_df)

        predicted = evaluation.correct_matches + evaluation.false_matches
        precision = evaluation.matching_precision if predicted else None
        false_rate = evaluation.false_match_rate if predicted else None
        recall = evaluation.exception_recall if evaluation.actual_exceptions else None

        evaluation_dict = {
            "total_records": evaluation.total_records,
            "matched_records": evaluation.matched_records,
            "exception_records": evaluation.exception_records,
            "correct_matches": evaluation.correct_matches,
            "false_matches": evaluation.false_matches,
            "false_alarms": evaluation.false_alarms,
            "missed_exceptions": evaluation.missed_exceptions,
            "detected_exceptions": evaluation.detected_exceptions,
            "actual_exceptions": evaluation.actual_exceptions,
            "match_rate": evaluation.match_rate,
            "matching_precision": precision,
            "exception_recall": recall,
            "false_match_rate": false_rate,
            "total_expected_amount": float(evaluation.total_expected_amount),
            "reconciled_amount": float(evaluation.reconciled_amount),
            "unresolved_amount": float(evaluation.unresolved_amount),
            "elapsed_seconds": evaluation.elapsed_seconds,
            "throughput_per_second": evaluation.throughput_per_second,
        }

        batch_id = uuid.uuid4().hex
        batch = Batch(
            id=batch_id,
            name="demo-seed-42",
            status="RECONCILED",
            orders_count=len(orders),
            payments_count=len(payments),
            settlements_count=len(settlements),
            refunds_count=len(refunds),
            has_ground_truth=True,
            elapsed_seconds=report.elapsed_seconds,
            evaluation_json=json.dumps(evaluation_dict),
            created_at=utc_now(),
            reconciled_at=utc_now(),
        )
        db.add(batch)

        for result in report.results:
            variance = result.variance if result.variance is not None else Decimal("0")
            row = TransactionResultRow(
                batch_id=batch_id,
                transaction_id=result.transaction_id,
                status=result.status,
                confidence=result.confidence,
                expected_amount=result.expected_amount,
                actual_amount=result.actual_amount,
                net_expected=result.net_expected,
                fee=result.fee,
                tax=result.tax,
                variance=variance,
                variance_abs_paise=int(round(abs(variance) * 100)),
                exception_type=result.exception_type.value,
                reason=result.reason,
                recommendation=result.recommendation,
                match_method=result.match_method,
                related_records="|".join(result.related_records),
            )
            db.add(row)

        db.commit()
        return batch_id
    finally:
        db.close()
