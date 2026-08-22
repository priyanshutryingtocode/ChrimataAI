from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

from app.models.transaction import TransactionResult
from app.reconciliation.engine import ReconciliationReport
from app.reconciliation.exceptions import ExceptionType


@dataclass(frozen=True)
class EvaluationReport:
    total_records: int
    matched_records: int
    exception_records: int
    correct_matches: int
    false_matches: int
    false_alarms: int
    missed_exceptions: int
    detected_exceptions: int
    actual_exceptions: int
    match_rate: float
    matching_precision: float
    exception_recall: float
    false_match_rate: float
    total_expected_amount: Decimal
    reconciled_amount: Decimal
    unresolved_amount: Decimal
    elapsed_seconds: float
    throughput_per_second: float


def evaluate(report: ReconciliationReport, ground_truth: pd.DataFrame) -> EvaluationReport:
    expected_types = _ground_truth_map(ground_truth)

    total = len(report.results)
    matched = 0
    exceptions = 0
    correct_matches = 0
    false_matches = 0
    missed = 0
    detected = 0
    false_alarms = 0
    actual_exception_count = 0

    for result in report.results:
        gt_type = expected_types.get(result.transaction_id, ExceptionType.NONE)
        predicted_match = result.status == "MATCHED"
        gt_exception = gt_type != ExceptionType.NONE

        if gt_exception:
            actual_exception_count += 1

        if predicted_match and not gt_exception:
            matched += 1
            correct_matches += 1
        elif predicted_match and gt_exception:
            matched += 1
            false_matches += 1
            if result.exception_type == gt_type:
                detected += 1
            else:
                missed += 1
        elif not predicted_match and gt_exception:
            exceptions += 1
            if result.exception_type == gt_type:
                detected += 1
            else:
                missed += 1
        else:
            exceptions += 1
            false_alarms += 1

    predicted_match_total = correct_matches + false_matches
    match_rate = matched / total if total else 0.0
    precision = correct_matches / predicted_match_total if predicted_match_total else 0.0
    recall = detected / actual_exception_count if actual_exception_count else 1.0
    false_match_rate = false_matches / predicted_match_total if predicted_match_total else 0.0

    total_amount = sum((r.expected_amount for r in report.results), Decimal("0"))
    reconciled_amount = sum(
        (r.expected_amount for r in report.results if r.status == "MATCHED"), Decimal("0")
    )
    elapsed = max(report.elapsed_seconds, 1e-9)
    throughput = total / elapsed

    return EvaluationReport(
        total_records=total,
        matched_records=matched,
        exception_records=exceptions,
        correct_matches=correct_matches,
        false_matches=false_matches,
        false_alarms=false_alarms,
        missed_exceptions=missed,
        detected_exceptions=detected,
        actual_exceptions=actual_exception_count,
        match_rate=match_rate,
        matching_precision=precision,
        exception_recall=recall,
        false_match_rate=false_match_rate,
        total_expected_amount=total_amount,
        reconciled_amount=reconciled_amount,
        unresolved_amount=total_amount - reconciled_amount,
        elapsed_seconds=report.elapsed_seconds,
        throughput_per_second=throughput,
    )


def _ground_truth_map(ground_truth: pd.DataFrame) -> dict[str, ExceptionType]:
    mapping: dict[str, ExceptionType] = {}
    for _, row in ground_truth.iterrows():
        transaction_id = str(row["transaction_id"]).strip().upper()
        raw_type = str(row["exception_type"]).strip().upper() or "NONE"
        mapping[transaction_id] = ExceptionType(raw_type)
    return mapping
