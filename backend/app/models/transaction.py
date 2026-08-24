from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.reconciliation.exceptions import ExceptionType


@dataclass(frozen=True)
class Order:
    order_id: str
    customer_id: str
    customer_name: str
    order_amount: Decimal
    currency: str
    order_date: date


@dataclass(frozen=True)
class Payment:
    payment_id: str
    order_id: str
    customer_id: str
    amount: Decimal
    currency: str
    payment_date: date
    payment_status: str


@dataclass(frozen=True)
class Settlement:
    settlement_id: str
    payment_id: str
    settlement_date: date
    gross_amount: Decimal
    processing_fee: Decimal
    tax: Decimal
    net_amount: Decimal
    currency: str


@dataclass(frozen=True)
class Refund:
    refund_id: str
    payment_id: str
    refund_amount: Decimal
    refund_date: date
    refund_status: str


@dataclass(frozen=True)
class SourceData:
    orders: list[Order]
    payments: list[Payment]
    settlements: list[Settlement]
    refunds: list[Refund]


@dataclass(frozen=True)
class TransactionResult:
    transaction_id: str
    status: str
    confidence: float
    expected_amount: Decimal
    actual_amount: Decimal | None
    net_expected: Decimal | None
    fee: Decimal | None
    tax: Decimal | None
    variance: Decimal
    exception_type: ExceptionType
    reason: str
    recommendation: str
    match_method: str
    related_records: tuple[str, ...] = ()
