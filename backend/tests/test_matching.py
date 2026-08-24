from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models.transaction import Order, Payment, Refund, Settlement, SourceData
from app.reconciliation.engine import run_reconciliation
from app.reconciliation.exceptions import ExceptionType
from app.reconciliation.rules import expected_fee, expected_tax, round_money

D1 = date(2026, 6, 1)
D2 = date(2026, 6, 2)


def make_order(order_id="ORD-00001", amount=Decimal("5000.00")) -> Order:
    return Order(
        order_id=order_id,
        customer_id="CUST-001",
        customer_name="Test Customer",
        order_amount=amount,
        currency="INR",
        order_date=D1,
    )


def make_payment(payment_id="PAY-00001", order_id="ORD-00001", amount=Decimal("5000.00")) -> Payment:
    return Payment(
        payment_id=payment_id,
        order_id=order_id,
        customer_id="CUST-001",
        amount=amount,
        currency="INR",
        payment_date=D1,
        payment_status="captured",
    )


def make_settlement(
    payment: Payment,
    settlement_id="SETL-00001",
    gross=None,
    fee=None,
    tax=None,
    net=None,
    settlement_date=D2,
    payment_id=None,
) -> Settlement:
    gross = payment.amount if gross is None else gross
    fee = expected_fee(gross) if fee is None else fee
    tax = expected_tax(fee) if tax is None else tax
    if net is None:
        net = gross - fee - tax
    return Settlement(
        settlement_id=settlement_id,
        payment_id=payment.payment_id if payment_id is None else payment_id,
        settlement_date=settlement_date,
        gross_amount=gross,
        processing_fee=fee,
        tax=tax,
        net_amount=net,
        currency="INR",
    )


def make_refund(
    payment: Payment,
    refund_id="REF-00001",
    amount=Decimal("500.00"),
    status="processed",
) -> Refund:
    return Refund(
        refund_id=refund_id,
        payment_id=payment.payment_id,
        refund_amount=amount,
        refund_date=D1,
        refund_status=status,
    )


def reconcile(payments, settlements, refunds=None, orders=None):
    source = SourceData(
        orders=orders if orders is not None else [],
        payments=payments,
        settlements=settlements,
        refunds=refunds or [],
    )
    report = run_reconciliation(source)
    return report.results


def single_result(results):
    assert len(results) == 1
    return results[0]


def test_exact_match():
    payment = make_payment()
    result = single_result(reconcile([payment], [make_settlement(payment)]))
    assert result.status == "MATCHED"
    assert result.exception_type == ExceptionType.NONE
    assert result.confidence == 1.0
    assert result.variance == Decimal("0.00")
    assert result.expected_amount == Decimal("5000.00")
    assert result.net_expected == result.actual_amount
    assert result.actual_amount == round_money(Decimal("5000") - expected_fee(Decimal("5000")) - expected_tax(expected_fee(Decimal("5000"))))


def test_missing_settlement():
    payment = make_payment()
    result = single_result(reconcile([payment], []))
    assert result.status == "EXCEPTION"
    assert result.exception_type == ExceptionType.MISSING_SETTLEMENT
    assert result.actual_amount is None
    assert result.net_expected is None


def test_amount_mismatch():
    payment = make_payment()
    gross = payment.amount + Decimal("264.00")
    settlement = make_settlement(payment, gross=gross)
    result = single_result(reconcile([payment], [settlement]))
    assert result.exception_type == ExceptionType.AMOUNT_MISMATCH
    assert result.variance == Decimal("-264.00")


def test_fee_mismatch():
    payment = make_payment()
    bad_fee = expected_fee(payment.amount) + Decimal("50.00")
    settlement = make_settlement(payment, fee=bad_fee, tax=expected_tax(bad_fee))
    result = single_result(reconcile([payment], [settlement]))
    assert result.exception_type == ExceptionType.FEE_MISMATCH


def test_tax_mismatch():
    payment = make_payment()
    fee = expected_fee(payment.amount)
    settlement = make_settlement(payment, fee=fee, tax=expected_tax(fee) + Decimal("30.00"))
    result = single_result(reconcile([payment], [settlement]))
    assert result.exception_type == ExceptionType.TAX_MISMATCH


def test_duplicate_payment_rows():
    payment = make_payment()
    settlement = make_settlement(payment)
    results = reconcile([payment, make_payment()], [settlement])
    result = single_result(results)
    assert result.exception_type == ExceptionType.DUPLICATE_TRANSACTION
    assert result.transaction_id == "PAY-00001"


def test_multiple_settlements_for_one_payment():
    payment = make_payment()
    first = make_settlement(payment, settlement_id="SETL-00001")
    second = make_settlement(payment, settlement_id="SETL-00002")
    result = single_result(reconcile([payment], [first, second]))
    assert result.exception_type == ExceptionType.DUPLICATE_TRANSACTION


def test_refund_not_settled():
    payment = make_payment()
    refund = make_refund(payment)
    settlement = make_settlement(payment)
    result = single_result(reconcile([payment], [settlement], refunds=[refund]))
    assert result.exception_type == ExceptionType.REFUND_NOT_SETTLED
    assert result.variance == -Decimal("500.00")


def test_valid_refund_deducted_matches():
    payment = make_payment()
    refund = make_refund(payment)
    settlement = make_settlement(payment, net=payment.amount - expected_fee(payment.amount) - expected_tax(expected_fee(payment.amount)) - Decimal("500.00"))
    result = single_result(reconcile([payment], [settlement], refunds=[refund]))
    assert result.status == "MATCHED"
    assert result.net_expected == result.actual_amount
    assert result.net_expected == payment.amount - expected_fee(payment.amount) - expected_tax(expected_fee(payment.amount)) - Decimal("500.00")


def test_pending_refund_ignored():
    payment = make_payment()
    refund = make_refund(payment, status="pending")
    settlement = make_settlement(payment)
    result = single_result(reconcile([payment], [settlement], refunds=[refund]))
    assert result.status == "MATCHED"


def test_date_mismatch():
    payment = make_payment()
    late = make_settlement(payment, settlement_date=date(2026, 7, 15))
    result = single_result(reconcile([payment], [late]))
    assert result.exception_type == ExceptionType.DATE_MISMATCH


def test_unknown_transaction():
    orphan = make_settlement(make_payment(), payment_id="PAY-99999")
    result = single_result(reconcile([], [orphan]))
    assert result.status == "EXCEPTION"
    assert result.exception_type == ExceptionType.UNKNOWN_TRANSACTION
    assert result.transaction_id == "SETL-00001"


def test_secondary_signal_matching():
    payment = make_payment(amount=Decimal("7000.00"))
    orphan = make_settlement(make_payment(), payment_id="PAY-77777", gross=Decimal("7000.00"))
    orders = [make_order(order_id="ORD-00001", amount=Decimal("7000.00"))]
    results = reconcile([payment], [orphan], orders=orders)
    result = single_result(results)
    assert result.match_method == "secondary_signals"
    assert result.confidence == pytest.approx(0.75)
    assert result.transaction_id == "PAY-00001"
