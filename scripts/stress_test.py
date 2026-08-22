from __future__ import annotations

import argparse
import sys
import tempfile
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
SCRIPTS_DIR = Path(__file__).resolve().parent
for path in (str(BACKEND_DIR), str(SCRIPTS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import generate_data
from app.core.formatting import format_inr
from app.reconciliation.engine import run_reconciliation
from app.reconciliation.metrics import evaluate
from app.reconciliation.normalize import load_ground_truth, load_source_data


@dataclass(frozen=True)
class StressResult:
    records: int
    seed: int
    injected_exceptions: int
    matched_records: int
    detected_exceptions: int
    match_rate: float
    precision: float
    recall: float
    false_match_rate: float
    false_alarms: int
    elapsed_seconds: float
    throughput_per_second: float
    total_amount: Decimal
    reconciled_amount: Decimal
    unresolved_amount: Decimal
    detected_breakdown: dict[str, int] = field(default_factory=dict)
    injected_breakdown: dict[str, int] = field(default_factory=dict)


def run_single(records: int, seed: int) -> StressResult:
    dataset = generate_data.generate_dataset(records, seed)

    with tempfile.TemporaryDirectory(prefix="stress_") as tmp:
        work_dir = Path(tmp)
        generated_dir = work_dir / "generated"
        ground_truth_dir = work_dir / "ground_truth"
        generate_data.write_dataset(dataset, generated_dir, ground_truth_dir)
        source = load_source_data(generated_dir)
        report = run_reconciliation(source)
        evaluation = evaluate(report, load_ground_truth(ground_truth_dir / "ground_truth.csv"))

    detected_breakdown: dict[str, int] = {}
    for result in report.results:
        if result.status == "EXCEPTION":
            key = result.exception_type.value
            detected_breakdown[key] = detected_breakdown.get(key, 0) + 1

    injected_breakdown: dict[str, int] = {}
    for row in dataset.ground_truth:
        exception_type = row["exception_type"]
        if exception_type != "NONE":
            injected_breakdown[exception_type] = injected_breakdown.get(exception_type, 0) + 1

    return StressResult(
        records=records,
        seed=seed,
        injected_exceptions=evaluation.actual_exceptions,
        matched_records=evaluation.matched_records,
        detected_exceptions=evaluation.exception_records,
        match_rate=evaluation.match_rate,
        precision=evaluation.matching_precision,
        recall=evaluation.exception_recall,
        false_match_rate=evaluation.false_match_rate,
        false_alarms=evaluation.false_alarms,
        elapsed_seconds=report.elapsed_seconds,
        throughput_per_second=evaluation.throughput_per_second,
        total_amount=evaluation.total_expected_amount,
        reconciled_amount=evaluation.reconciled_amount,
        unresolved_amount=evaluation.unresolved_amount,
        detected_breakdown=detected_breakdown,
        injected_breakdown=injected_breakdown,
    )


def parse_int_list(text: str) -> list[int]:
    return [int(item.strip()) for item in text.split(",") if item.strip()]


def print_table(results: list[StressResult]) -> None:
    header = (
        f"{'Records':>8} {'Seed':>5} {'Inj.':>5} {'Found':>6} {'Match%':>8} "
        f"{'Prec%':>7} {'Recall%':>8} {'FalseM%':>8} {'Elapsed':>9} {'Throughput':>11}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r.records:>8} {r.seed:>5} {r.injected_exceptions:>5} {r.detected_exceptions:>6} "
            f"{r.match_rate * 100:>7.2f}% {r.precision * 100:>6.2f}% {r.recall * 100:>7.2f}% "
            f"{r.false_match_rate * 100:>7.2f}% {r.elapsed_seconds:>8.4f}s {r.throughput_per_second:>9.0f}/s"
        )


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Run the reconciliation engine across a size x seed matrix.")
    parser.add_argument("--sizes", type=parse_int_list, default=[500, 1000])
    parser.add_argument("--seeds", type=parse_int_list, default=[42, 7, 123])
    args = parser.parse_args()

    results: list[StressResult] = []
    for size in args.sizes:
        for seed in args.seeds:
            print(f"Running records={size} seed={seed} …")
            results.append(run_single(size, seed))

    print()
    print_table(results)
    print()

    failures = [
        r for r in results if r.precision != 1.0 or r.false_match_rate != 0.0 or r.false_alarms != 0
    ]
    if failures:
        print(f"HONESTY GATE FAILED: {len(failures)} configuration(s) with precision loss or false alarms.")
        raise SystemExit(1)
    print("HONESTY GATE PASSED: 100% precision, zero false matches and zero false alarms on every configuration.")


if __name__ == "__main__":
    main()
