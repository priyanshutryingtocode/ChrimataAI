from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from app.reconciliation.exceptions import ExceptionType


class ProposalKind(str, Enum):
    ADJUSTMENT = "ADJUSTMENT"
    VENDOR_QUERY = "VENDOR_QUERY"
    MARK_AS_VALID = "MARK_AS_VALID"
    LINK_RECORD = "LINK_RECORD"
    RETRY_RECONCILIATION = "RETRY_RECONCILIATION"


ALLOWED_KINDS: dict[ExceptionType, frozenset[ProposalKind]] = {
    ExceptionType.AMOUNT_MISMATCH: frozenset({ProposalKind.ADJUSTMENT, ProposalKind.VENDOR_QUERY}),
    ExceptionType.FEE_MISMATCH: frozenset({ProposalKind.ADJUSTMENT, ProposalKind.VENDOR_QUERY}),
    ExceptionType.TAX_MISMATCH: frozenset({ProposalKind.ADJUSTMENT, ProposalKind.VENDOR_QUERY}),
    ExceptionType.MISSING_SETTLEMENT: frozenset({ProposalKind.VENDOR_QUERY, ProposalKind.RETRY_RECONCILIATION}),
    ExceptionType.REFUND_NOT_SETTLED: frozenset({ProposalKind.VENDOR_QUERY, ProposalKind.RETRY_RECONCILIATION}),
    ExceptionType.DUPLICATE_TRANSACTION: frozenset({ProposalKind.LINK_RECORD, ProposalKind.VENDOR_QUERY}),
    ExceptionType.DATE_MISMATCH: frozenset({ProposalKind.MARK_AS_VALID, ProposalKind.VENDOR_QUERY}),
    ExceptionType.UNKNOWN_TRANSACTION: frozenset({ProposalKind.LINK_RECORD, ProposalKind.VENDOR_QUERY}),
}


@dataclass(frozen=True)
class FinancialEffect:
    financial_status: str
    reconciled_adjustment_amount: Decimal
    event: str


def default_proposal_kind(exception_type: ExceptionType) -> ProposalKind:
    if exception_type in (
        ExceptionType.AMOUNT_MISMATCH,
        ExceptionType.FEE_MISMATCH,
        ExceptionType.TAX_MISMATCH,
    ):
        return ProposalKind.ADJUSTMENT
    if exception_type == ExceptionType.DATE_MISMATCH:
        return ProposalKind.MARK_AS_VALID
    return ProposalKind.VENDOR_QUERY


def proposed_amount_for(kind: ProposalKind, variance: Decimal) -> Decimal:
    if kind == ProposalKind.MARK_AS_VALID:
        return Decimal("0")
    return abs(variance)


def validate_proposal_kind(kind: ProposalKind, exception_type: ExceptionType, variance: Decimal) -> str | None:
    if kind not in ALLOWED_KINDS[exception_type]:
        return f"{kind.value} is not allowed for {exception_type.value}"
    if kind == ProposalKind.MARK_AS_VALID:
        if exception_type != ExceptionType.DATE_MISMATCH:
            return f"MARK_AS_VALID is only permitted for DATE_MISMATCH, not {exception_type.value}"
        if abs(variance) > Decimal("0"):
            return "MARK_AS_VALID requires zero monetary variance"
    if kind == ProposalKind.ADJUSTMENT and abs(variance) <= Decimal("0"):
        return "ADJUSTMENT requires a non-zero variance"
    return None


def validate_proposal_amount(kind: ProposalKind, amount: Decimal, variance: Decimal) -> str | None:
    if amount < Decimal("0"):
        return "amount cannot be negative"
    if kind == ProposalKind.MARK_AS_VALID:
        if amount != Decimal("0"):
            return "MARK_AS_VALID amount must be zero"
        return None
    if kind == ProposalKind.ADJUSTMENT:
        if amount <= Decimal("0"):
            return "ADJUSTMENT amount must be greater than zero"
        if amount > abs(variance):
            return f"ADJUSTMENT amount {amount} exceeds outstanding variance {abs(variance)}"
        return None
    if amount > abs(variance):
        return f"amount {amount} exceeds outstanding variance {abs(variance)}"
    return None


def apply_financial_effect(
    kind: ProposalKind,
    approved_amount: Decimal,
    variance: Decimal,
    financial_status: str,
) -> FinancialEffect:
    if financial_status == "RECONCILED":
        return FinancialEffect("RECONCILED", Decimal("0"), "ALREADY_RECONCILED")

    if kind == ProposalKind.ADJUSTMENT:
        outstanding = abs(variance)
        applied = approved_amount
        new_status = "RECONCILED" if applied >= outstanding else "UNRESOLVED"
        return FinancialEffect(new_status, applied, "ADJUSTMENT_APPLIED")

    if kind == ProposalKind.MARK_AS_VALID:
        return FinancialEffect("RECONCILED", Decimal("0"), "MARKED_AS_VALID")

    return FinancialEffect("UNRESOLVED", Decimal("0"), "NO_FINANCIAL_EFFECT")
