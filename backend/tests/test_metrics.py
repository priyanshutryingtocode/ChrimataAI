from __future__ import annotations

from decimal import Decimal

import pandas as pd

from app.models.transaction import TransactionResult
from app.reconciliation.engine import ReconciliationReport
from app.reconciliation.exceptions import ExceptionType
from app.reconciliation.metrics import evaluate


def make_result(
    transaction_id: str,
    status: str,
    exception_type: ExceptionType = ExceptionType.NONE,
    expected_amount: Decimal = Decimal("1000.00"),
    variance: Decimal = Decimal("0.00"),
) -> TransactionResult:
    return TransactionResult(
        transaction_id=transaction_id,
        status=status,
        confidence=1.0,
        expected_amount=expected_amount,
        actual_amount=expected_amount - variance if status == "MATCHED" else expected_amount,
        net_expected=expected_amount - variance if status == "MATCHED" else expected_amount,
        fee=Decimal("20.00"),
        tax=Decimal("3.60"),
        variance=variance,
        exception_type=exception_type,
        reason="test",
        recommendation="",
        match_method="payment_id",
        related_records=(transaction_id,),
    )


def make_ground_truth(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"transaction_id": transaction_id, "exception_type": exception_type}
            for transaction_id, exception_type in rows
        ]
    )


def evaluate_results(results, truth_rows):
    report = ReconciliationReport(results=list(results), elapsed_seconds=2.0)
    return evaluate(report, make_ground_truth(truth_rows))


def test_perfect_batch_scores_full_marks():
    results = [
        make_result("PAY-00001", "MATCHED"),
        make_result("PAY-00002", "MATCHED"),
        make_result("PAY-00003", "EXCEPTION", ExceptionType.AMOUNT_MISMATCH),
    ]
    truth = [
        ("PAY-00001", "NONE"),
        ("PAY-00002", "NONE"),
        ("PAY-00003", "AMOUNT_MISMATCH"),
    ]
    evaluation = evaluate_results(results, truth)
    assert evaluation.total_records == 3
    assert evaluation.match_rate == 2 / 3
    assert evaluation.matching_precision == 1.0
    assert evaluation.exception_recall == 1.0
    assert evaluation.false_match_rate == 0.0
    assert evaluation.actual_exceptions == 1
    assert evaluation.detected_exceptions == 1
    assert evaluation.throughput_per_second == 1.5


def test_false_match_is_counted():
    results = [
        make_result("PAY-00001", "MATCHED"),
        make_result("PAY-00002", "MATCHED"),
    ]
    truth = [("PAY-00001", "NONE"), ("PAY-00002", "MISSING_SETTLEMENT")]
    evaluation = evaluate_results(results, truth)
    assert evaluation.false_matches == 1
    assert evaluation.matching_precision == 0.5
    assert evaluation.false_match_rate == 0.5
    assert evaluation.missed_exceptions == 1


def test_wrong_subtype_counts_as_missed_exception():
    results = [make_result("PAY-00001", "EXCEPTION", ExceptionType.TAX_MISMATCH)]
    truth = [("PAY-00001", "FEE_MISMATCH")]
    evaluation = evaluate_results(results, truth)
    assert evaluation.detected_exceptions == 0
    assert evaluation.exception_recall == 0.0


def test_false_alarm_does_not_affect_recall():
    results = [make_result("PAY-00001", "EXCEPTION", ExceptionType.DATE_MISMATCH)]
    truth = [("PAY-00001", "NONE")]
    evaluation = evaluate_results(results, truth)
    assert evaluation.false_alarms == 1
    assert evaluation.matching_precision == 0.0
    assert evaluation.false_match_rate == 0.0


def test_amount_totals():
    results = [
        make_result("PAY-00001", "MATCHED", expected_amount=Decimal("400.00")),
        make_result("PAY-00002", "EXCEPTION", ExceptionType.MISSING_SETTLEMENT, expected_amount=Decimal("600.00")),
    ]
    truth = [("PAY-00001", "NONE"), ("PAY-00002", "MISSING_SETTLEMENT")]
    evaluation = evaluate_results(results, truth)
    assert evaluation.total_expected_amount == Decimal("1000.00")
    assert evaluation.reconciled_amount == Decimal("400.00")
    assert evaluation.unresolved_amount == Decimal("600.00")
