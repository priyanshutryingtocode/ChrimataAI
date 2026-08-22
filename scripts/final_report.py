from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
SCRIPTS_DIR = Path(__file__).resolve().parent
for path in (str(BACKEND_DIR), str(SCRIPTS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import stress_test
from app.core.formatting import format_inr

REPORTS_DIR = BACKEND_DIR / "data" / "reports"


def build_report(results: list[stress_test.StressResult]) -> str:
    lines: list[str] = []
    lines.append("AI FINANCE CONTROLLER - FINAL EVALUATION REPORT")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    lines.append("=" * 78)
    lines.append("")
    lines.append(
        f"{'Records':>8} {'Seed':>5} | {'Match%':>8} {'Prec%':>7} {'Recall%':>8} {'FalseM%':>8} "
        f"{'FalseAlm':>8} {'Elapsed':>9} {'Throughput':>11}"
    )
    lines.append("-" * 96)

    for r in results:
        lines.append(
            f"{r.records:>8} {r.seed:>5} | {r.match_rate * 100:>7.2f}% {r.precision * 100:>6.2f}% "
            f"{r.recall * 100:>7.2f}% {r.false_match_rate * 100:>7.2f}% {r.false_alarms:>8} "
            f"{r.elapsed_seconds:>8.4f}s {r.throughput_per_second:>9.0f}/s"
        )

    total_records = sum(r.records for r in results)
    total_injected = sum(r.injected_exceptions for r in results)
    total_detected = sum(r.detected_exceptions for r in results)
    total_amount = sum((r.total_amount for r in results), Decimal("0"))
    reconciled_amount = sum((r.reconciled_amount for r in results), Decimal("0"))

    lines.append("-" * 96)
    lines.append(
        f"TOTALS: {total_records} records across {len(results)} configurations · "
        f"{total_injected} injected exceptions, {total_detected} detected"
    )
    lines.append(f"Amounts: processed {format_inr(total_amount)} · reconciled {format_inr(reconciled_amount)}")

    lines.append("")
    lines.append("EXCEPTION DETECTION BY TYPE (injected vs detected)")
    lines.append("-" * 96)
    all_types = sorted(
        {key for r in results for key in list(r.injected_breakdown) + list(r.detected_breakdown)}
    )
    lines.append(f"{'Type':<26}" + "".join(f"  {r.records}@{r.seed}".rjust(14) for r in results))
    for exception_type in all_types:
        cells = []
        for r in results:
            injected = r.injected_breakdown.get(exception_type, 0)
            detected = r.detected_breakdown.get(exception_type, 0)
            cells.append(f"{injected:>4}->{detected:<4}".rjust(14))
        lines.append(f"{exception_type:<26}" + "".join(cells))

    lines.append("")
    lines.append("METHODOLOGY")
    lines.append("-" * 96)
    lines.append("* Deterministic reconciliation engine; no LLM involvement in matching or scoring.")
    lines.append("* Ground truth generated alongside data with fixed seeds; never exposed to the engine.")
    lines.append("* Precision = correct matches / predicted matches. Exception recall uses exact subtype match.")
    lines.append("* False-match rate = incorrectly matched / all matched. False alarms counted separately.")
    lines.append("* Same seed always reproduces the same dataset and the same report.")

    return "\n".join(lines) + "\n"


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Produce the final evaluation report.")
    parser.add_argument("--sizes", type=stress_test.parse_int_list, default=[100, 500, 1000])
    parser.add_argument("--seeds", type=stress_test.parse_int_list, default=[42, 7])
    parser.add_argument("--out", type=Path, default=REPORTS_DIR / "final_report.txt")
    args = parser.parse_args()

    results: list[stress_test.StressResult] = []
    for size in args.sizes:
        for seed in args.seeds:
            print(f"Evaluating records={size} seed={seed} …")
            results.append(stress_test.run_single(size, seed))

    report_text = build_report(results)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report_text, encoding="utf-8")

    print()
    print(report_text)
    print(f"Report saved to: {args.out}")

    failures = [
        r for r in results if r.precision != 1.0 or r.false_match_rate != 0.0 or r.false_alarms != 0
    ]
    if failures:
        print(f"HONESTY GATE FAILED on {len(failures)} configuration(s).")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
