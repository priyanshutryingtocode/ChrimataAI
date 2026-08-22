from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal

from app.models.transaction import Settlement, SourceData, TransactionResult
from app.reconciliation.exceptions import (
    RECOMMENDATIONS,
    ExceptionType,
    classify,
)
from app.reconciliation.matcher import MatchOutput, PaymentMatch, build_matches
from app.reconciliation.rules import (
    DATE_TOLERANCE_DAYS,
    FEE_RATE,
    TAX_RATE,
    days_between,
    expected_fee,
    expected_tax,
    round_money,
    within_tolerance,
)


@dataclass(frozen=True)
class ReconciliationReport:
    results: list[TransactionResult]
    elapsed_seconds: float

    @property
    def total_records(self) -> int:
        return len(self.results)


def run_reconciliation(source: SourceData) -> ReconciliationReport:
    started = time.perf_counter()
    output = build_matches(source.payments, source.settlements, source.refunds, source.orders)
    results = [_reconcile_payment(match) for match in output.payment_matches]
    results.extend(_reconcile_orphan(settlement) for settlement in output.orphan_settlements)
    elapsed = time.perf_counter() - started
    return ReconciliationReport(results=results, elapsed_seconds=elapsed)


def _fmt(amount: Decimal | None) -> str:
    if amount is None:
        return "N/A"
    return f"Rs.{round_money(amount)}"


def _reconcile_payment(match: PaymentMatch) -> TransactionResult:
    payment = match.payment
    findings: set[ExceptionType] = set()
    reasons: list[str] = []

    if match.duplicate_payment_rows > 1:
        findings.add(ExceptionType.DUPLICATE_TRANSACTION)
        reasons.append(
            f"payment_id {payment.payment_id} appears {match.duplicate_payment_rows} times in payments."
        )

    settlement = match.settlements[0] if match.settlements else None

    if len(match.settlements) > 1:
        findings.add(ExceptionType.DUPLICATE_TRANSACTION)
        reasons.append(
            f"{len(match.settlements)} settlements reference payment_id {payment.payment_id}."
        )

    if settlement is None:
        findings.add(ExceptionType.MISSING_SETTLEMENT)
        reasons.append(f"No settlement record found for payment {payment.payment_id}.")
    else:
        _verify_financials(payment, match, settlement, findings, reasons)

    exception_type = classify(findings)
    status = "EXCEPTION" if exception_type != ExceptionType.NONE else "MATCHED"

    refund_total = sum((refund.refund_amount for refund in match.valid_refunds), Decimal("0"))
    variance = Decimal("0")
    if settlement is not None:
        expected_net = payment.amount - refund_total - (settlement.processing_fee or Decimal("0")) - (settlement.tax or Decimal("0"))
        variance = round_money(expected_net - settlement.net_amount)

    return TransactionResult(
        transaction_id=payment.payment_id,
        status=status,
        confidence=match.confidence,
        expected_amount=payment.amount,
        actual_amount=settlement.net_amount if settlement else None,
        fee=settlement.processing_fee if settlement else None,
        tax=settlement.tax if settlement else None,
        variance=variance,
        exception_type=exception_type,
        reason=" ".join(reasons) if reasons else "Settlement equals payment amount after fee, tax and refunds.",
        recommendation="" if not findings else RECOMMENDATIONS[exception_type],
        match_method=match.match_method,
        related_records=_related_records(match),
    )


def _verify_financials(
    payment,
    match: PaymentMatch,
    settlement: Settlement,
    findings: set[ExceptionType],
    reasons: list[str],
) -> None:
    if not within_tolerance(settlement.gross_amount, payment.amount):
        findings.add(ExceptionType.AMOUNT_MISMATCH)
        delta = round_money(settlement.gross_amount - payment.amount)
        reasons.append(
            f"Settlement gross {_fmt(settlement.gross_amount)} differs from payment amount {_fmt(payment.amount)} by {_fmt(delta)}."
        )

    scheduled_fee = expected_fee(payment.amount)
    if not within_tolerance(settlement.processing_fee, scheduled_fee):
        findings.add(ExceptionType.FEE_MISMATCH)
        reasons.append(
            f"Recorded fee {_fmt(settlement.processing_fee)} differs from scheduled fee {_fmt(scheduled_fee)} ({FEE_RATE * 100}% of gross)."
        )

    fee_basis = settlement.processing_fee if within_tolerance(settlement.processing_fee, scheduled_fee) else scheduled_fee
    scheduled_tax = expected_tax(fee_basis)
    if not within_tolerance(settlement.tax, scheduled_tax):
        findings.add(ExceptionType.TAX_MISMATCH)
        reasons.append(
            f"Recorded tax {_fmt(settlement.tax)} differs from scheduled tax {_fmt(scheduled_tax)} ({TAX_RATE * 100}% of fee)."
        )

    if match.valid_refunds:
        refund_total = sum((refund.refund_amount for refund in match.valid_refunds), Decimal("0"))
        expected_net = settlement.gross_amount - settlement.processing_fee - settlement.tax - refund_total
        if not within_tolerance(settlement.net_amount, expected_net):
            findings.add(ExceptionType.REFUND_NOT_SETTLED)
            reasons.append(
                f"{len(match.valid_refunds)} processed refund(s) totalling {_fmt(refund_total)} were not deducted from the settlement net {_fmt(settlement.net_amount)}."
            )

    lag = days_between(settlement.settlement_date, payment.payment_date)
    if lag > DATE_TOLERANCE_DAYS:
        findings.add(ExceptionType.DATE_MISMATCH)
        reasons.append(
            f"Settled {lag} days after payment, beyond the {DATE_TOLERANCE_DAYS}-day tolerance window."
        )


def _related_records(match: PaymentMatch) -> tuple[str, ...]:
    records = []
    if match.order is not None:
        records.append(match.order.order_id)
    records.append(match.payment.payment_id)
    records.extend(settlement.settlement_id for settlement in sorted(match.settlements, key=lambda s: s.settlement_id))
    records.extend(refund.refund_id for refund in match.valid_refunds)
    return tuple(records)


def _reconcile_orphan(settlement: Settlement) -> TransactionResult:
    return TransactionResult(
        transaction_id=settlement.settlement_id,
        status="EXCEPTION",
        confidence=1.0,
        expected_amount=Decimal("0"),
        actual_amount=settlement.net_amount,
        fee=settlement.processing_fee,
        tax=settlement.tax,
        variance=round_money(settlement.net_amount),
        exception_type=ExceptionType.UNKNOWN_TRANSACTION,
        reason=f"No payment record exists for referenced payment_id {settlement.payment_id}.",
        recommendation=RECOMMENDATIONS[ExceptionType.UNKNOWN_TRANSACTION],
        match_method="none",
        related_records=(settlement.settlement_id,),
    )
