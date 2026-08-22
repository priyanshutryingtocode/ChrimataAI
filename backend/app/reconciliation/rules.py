from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

FEE_RATE = Decimal("0.02")
TAX_RATE = Decimal("0.18")
MONEY_QUANTUM = Decimal("0.01")
VARIANCE_TOLERANCE = Decimal("0.01")
DATE_TOLERANCE_DAYS = 2
SECONDARY_AMOUNT_WINDOW = Decimal("1.00")
SECONDARY_DATE_WINDOW_DAYS = 3
EXACT_MATCH_CONFIDENCE = 1.0
SECONDARY_MATCH_CONFIDENCE = 0.75
VALID_REFUND_STATUSES = frozenset({"processed"})


def round_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def expected_fee(gross_amount: Decimal) -> Decimal:
    return round_money(gross_amount * FEE_RATE)


def expected_tax(processing_fee: Decimal) -> Decimal:
    return round_money(processing_fee * TAX_RATE)


def is_valid_refund_status(status: str) -> bool:
    return status.strip().lower() in VALID_REFUND_STATUSES


def within_tolerance(actual: Decimal | None, expected: Decimal) -> bool:
    return actual is not None and abs(actual - expected) <= VARIANCE_TOLERANCE


def days_between(later: object, earlier: object) -> int:
    if later is None or earlier is None:
        return 0
    return abs((later - earlier).days)
