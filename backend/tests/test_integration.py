from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import generate_data
from app.reconciliation.engine import run_reconciliation
from app.reconciliation.exceptions import ExceptionType
from app.reconciliation.metrics import evaluate
from app.reconciliation.normalize import load_ground_truth, load_source_data

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

RECORDS = 100
SEED = 42


def build_and_evaluate(tmp_path: Path):
    dataset = generate_data.generate_dataset(RECORDS, SEED)
    generated_dir = tmp_path / "generated"
    ground_truth_dir = tmp_path / "ground_truth"
    generate_data.write_dataset(dataset, generated_dir, ground_truth_dir)

    source = load_source_data(generated_dir)
    report = run_reconciliation(source)
    evaluation = evaluate(report, load_ground_truth(ground_truth_dir / "ground_truth.csv"))
    return dataset, source, report, evaluation


def test_integration_pipeline_detects_every_injected_anomaly(tmp_path):
    _, _, report, evaluation = build_and_evaluate(tmp_path)

    assert report.total_records == RECORDS
    assert len({r.transaction_id for r in report.results}) == RECORDS

    assert evaluation.matching_precision == 1.0
    assert evaluation.exception_recall == 1.0
    assert evaluation.false_match_rate == 0.0
    assert evaluation.false_alarms == 0
    assert evaluation.match_rate == (RECORDS - evaluation.actual_exceptions) / RECORDS


def test_integration_injected_distribution_matches_generator(tmp_path):
    dataset, _, _, _ = build_and_evaluate(tmp_path)
    expected_counts = Counter(row["exception_type"] for row in dataset.ground_truth)
    assert sum(expected_counts.values()) == RECORDS
    allocation = generate_data.allocate_counts(RECORDS)
    for label, fraction in generate_data.ANOMALY_FRACTIONS:
        ground_truth_label = "NONE" if label == "CLEAN" else ExceptionType(label).value
        assert expected_counts[ground_truth_label] == allocation[label]


def test_integration_deterministic_output(tmp_path):
    first = generate_data.generate_dataset(RECORDS, SEED)
    second = generate_data.generate_dataset(RECORDS, SEED)
    assert first.ground_truth == second.ground_truth
    assert first.payments == second.payments
    assert first.settlements == second.settlements
    assert first.orders == second.orders
    assert first.refunds == second.refunds


def test_stress_runner_small_configuration():
    import stress_test

    result = stress_test.run_single(40, 42)

    assert result.records == 40
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.false_match_rate == 0.0
    assert result.false_alarms == 0
    assert result.detected_exceptions == result.injected_exceptions
    assert result.detected_breakdown == result.injected_breakdown
