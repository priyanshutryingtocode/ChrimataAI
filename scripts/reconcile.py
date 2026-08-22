from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.reconciliation.engine import run_reconciliation
from app.reconciliation.exceptions import ExceptionType
from app.reconciliation.metrics import evaluate
from app.reconciliation.normalize import load_ground_truth, load_source_data


def format_inr(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    quantized = abs(value).quantize(Decimal("0.01"))
    digits = f"{quantized:f}"
    whole, _, fraction = digits.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.append(head[-2:])
            head = head[:-2]
        if head:
            groups.append(head)
        whole = ",".join(reversed(groups)) + "," + tail
    return f"{sign}\u20b9{whole}.{fraction}"


def print_report(evaluation, results) -> None:
    exceptions = [r for r in results if r.status == "EXCEPTION"]
    exceptions.sort(key=lambda r: (-abs(r.variance), r.transaction_id))

    print("RECONCILIATION COMPLETE")
    print()
    print(f"Records processed:  {evaluation.total_records:>8}")
    print(f"Matched:            {evaluation.matched_records:>8}")
    print(f"Exceptions:         {evaluation.exception_records:>8}")
    print()
    print(f"Match rate:          {evaluation.match_rate * 100:>9.2f}%")
    print(f"Matching precision:  {evaluation.matching_precision * 100:>9.2f}%")
    print(f"Exception recall:    {evaluation.exception_recall * 100:>9.2f}%")
    print(f"False match rate:    {evaluation.false_match_rate * 100:>9.2f}%")
    print()
    elapsed = evaluation.elapsed_seconds
    time_text = f"{elapsed:.2f}" if elapsed >= 0.01 else f"{elapsed:.4f}"
    print(f"Processing time:     {time_text:>9} sec")
    print(f"Throughput:          {evaluation.throughput_per_second:>6.0f} records/sec")
    print()
    print(f"Reconciled amount:  {format_inr(evaluation.reconciled_amount):>15}")
    print(f"Unresolved amount:  {format_inr(evaluation.unresolved_amount):>15}")
    print()

    if exceptions:
        print("EXCEPTIONS")
        print()
        for position, result in enumerate(exceptions, start=1):
            variance_text = format_inr(result.variance)
            print(
                f"{position:>3}. {result.transaction_id:<12}"
                f"{result.exception_type.value:<24}variance {variance_text}"
            )


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Run deterministic reconciliation over generated data.")
    parser.add_argument("--data-dir", type=Path, default=BACKEND_DIR / "data" / "generated")
    parser.add_argument("--ground-truth", type=Path, default=BACKEND_DIR / "data" / "ground_truth" / "ground_truth.csv")
    args = parser.parse_args()

    source = load_source_data(args.data_dir)
    report = run_reconciliation(source)

    ground_truth_path = args.ground_truth
    if ground_truth_path.exists():
        evaluation = evaluate(report, load_ground_truth(ground_truth_path))
    else:
        raise SystemExit(f"Ground truth file not found: {ground_truth_path}")

    print_report(evaluation, report.results)


if __name__ == "__main__":
    main()
