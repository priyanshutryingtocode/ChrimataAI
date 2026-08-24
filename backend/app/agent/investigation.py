from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import tools
from app.core.batchfiles import generated_dir
from app.models.batch import TransactionResultRow
from app.reconciliation.normalize import (
    load_orders,
    load_payments,
    load_refunds,
    load_settlements,
)
from app.reconciliation.rules import expected_fee, expected_tax


def build_evidence_pack(db: Session, batch_id: str, transaction_id: str) -> dict | None:
    row = db.scalar(
        select(TransactionResultRow).where(
            TransactionResultRow.batch_id == batch_id,
            TransactionResultRow.transaction_id == transaction_id,
        )
    )
    if row is None:
        return None

    related = [item for item in row.related_records.split("|") if item]
    source_records = _collect_source_records(batch_id, transaction_id, related)

    scheduled_fee = expected_fee(row.expected_amount or Decimal("0"))
    scheduled_tax = expected_tax(scheduled_fee)

    same_type_rows = db.scalars(
        select(TransactionResultRow)
        .where(TransactionResultRow.batch_id == batch_id)
        .where(TransactionResultRow.status == "EXCEPTION")
        .where(TransactionResultRow.exception_type == row.exception_type)
    ).all()
    variance = abs(row.variance or Decimal("0"))
    worse = sum(1 for other in same_type_rows if abs(other.variance or Decimal("0")) > variance)
    percentile = round(100.0 * worse / len(same_type_rows), 1) if same_type_rows else 0.0

    return {
        "exception": {
            "transaction_id": row.transaction_id,
            "batch_id": row.batch_id,
            "exception_type": row.exception_type,
            "status": row.status,
            "confidence": row.confidence,
            "expected_amount": _money(row.expected_amount),
            "net_expected": _money(row.net_expected),
            "actual_amount": _money(row.actual_amount),
            "fee": _money(row.fee),
            "tax": _money(row.tax),
            "variance": _money(row.variance),
            "reason": row.reason,
            "match_method": row.match_method,
            "related_records": related,
        },
        "fee_tax_schedule_check": {
            "scheduled_fee": str(scheduled_fee),
            "recorded_fee": _money(row.fee),
            "scheduled_tax": str(scheduled_tax),
            "recorded_tax": _money(row.tax),
            "fee_matches_schedule": _money(row.fee) == str(scheduled_fee),
            "tax_matches_schedule": _money(row.tax) == str(scheduled_tax),
        },
        "batch_context": {
            "exception_type_distribution": tools.get_exception_type_distribution(db, batch_id),
            "same_type_exception_count": len(same_type_rows),
            "variance_percentile_within_type": percentile,
        },
        "related_source_records": source_records,
    }


def _money(value: Decimal | None) -> str:
    return "" if value is None else f"{value.quantize(Decimal('0.01'))}"


def _collect_source_records(batch_id: str, transaction_id: str, related: list[str]) -> dict:
    source_dir = generated_dir(batch_id)
    result: dict[str, list[dict]] = {"orders": [], "payments": [], "settlements": [], "refunds": []}
    if not (source_dir / "payments.csv").exists():
        return result

    related_set = {item.upper() for item in related}
    related_set.add(transaction_id.upper())

    for payment in load_payments(source_dir / "payments.csv"):
        if payment.payment_id in related_set:
            result["payments"].append(
                {
                    "payment_id": payment.payment_id,
                    "order_id": payment.order_id,
                    "customer_id": payment.customer_id,
                    "amount": str(payment.amount),
                    "currency": payment.currency,
                    "payment_date": payment.payment_date.isoformat() if payment.payment_date else "",
                    "payment_status": payment.payment_status,
                }
            )

    for settlement in load_settlements(source_dir / "settlements.csv"):
        if settlement.payment_id in related_set or settlement.settlement_id in related_set:
            result["settlements"].append(
                {
                    "settlement_id": settlement.settlement_id,
                    "payment_id": settlement.payment_id,
                    "settlement_date": settlement.settlement_date.isoformat() if settlement.settlement_date else "",
                    "gross_amount": str(settlement.gross_amount),
                    "processing_fee": str(settlement.processing_fee),
                    "tax": str(settlement.tax),
                    "net_amount": str(settlement.net_amount),
                    "currency": settlement.currency,
                }
            )

    for refund in load_refunds(source_dir / "refunds.csv"):
        if refund.payment_id in related_set or refund.refund_id in related_set:
            result["refunds"].append(
                {
                    "refund_id": refund.refund_id,
                    "payment_id": refund.payment_id,
                    "refund_amount": str(refund.refund_amount),
                    "refund_date": refund.refund_date.isoformat() if refund.refund_date else "",
                    "refund_status": refund.refund_status,
                }
            )

    for order in load_orders(source_dir / "orders.csv"):
        if order.order_id in related_set:
            result["orders"].append(
                {
                    "order_id": order.order_id,
                    "customer_id": order.customer_id,
                    "customer_name": order.customer_name,
                    "order_amount": str(order.order_amount),
                    "currency": order.currency,
                    "order_date": order.order_date.isoformat() if order.order_date else "",
                }
            )

    return result


def _try_load(loader):
    try:
        return loader()
    except Exception:
        return []
