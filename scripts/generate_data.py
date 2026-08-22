from __future__ import annotations

import argparse
import csv
import random
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.reconciliation.exceptions import ExceptionType
from app.reconciliation.rules import expected_fee, expected_tax, round_money

BASE_DATE = date(2026, 6, 1)
AMOUNT_MIN = 500
AMOUNT_MAX = 50_000
REFUND_RATE = 0.15
CUSTOMERS = [
    "Aarav Sharma",
    "Diya Patel",
    "Kabir Singh",
    "Ishaan Verma",
    "Ananya Iyer",
    "Vihaan Gupta",
    "Meera Nair",
    "Arjun Reddy",
    "Saanvi Joshi",
    "Rohan Mehta",
]

ANOMALY_FRACTIONS: list[tuple[str, float]] = [
    ("CLEAN", 0.70),
    ("AMOUNT_MISMATCH", 0.10),
    ("MISSING_SETTLEMENT", 0.05),
    ("DUPLICATE_TRANSACTION", 0.05),
    ("FEE_MISMATCH", 0.03),
    ("TAX_MISMATCH", 0.03),
    ("REFUND_NOT_SETTLED", 0.02),
    ("DATE_MISMATCH", 0.01),
    ("UNKNOWN_TRANSACTION", 0.01),
]

ORDER_FIELDS = ["order_id", "customer_id", "customer_name", "order_amount", "currency", "order_date"]
PAYMENT_FIELDS = ["payment_id", "order_id", "customer_id", "amount", "currency", "payment_date", "payment_status"]
SETTLEMENT_FIELDS = ["settlement_id", "payment_id", "settlement_date", "gross_amount", "processing_fee", "tax", "net_amount", "currency"]
REFUND_FIELDS = ["refund_id", "payment_id", "refund_amount", "refund_date", "refund_status"]
GROUND_TRUTH_FIELDS = [
    "transaction_id",
    "expected_status",
    "exception_type",
    "expected_settlement",
    "actual_settlement",
    "expected_variance",
    "source_records",
]


@dataclass
class GeneratedDataset:
    orders: list[dict[str, str]] = field(default_factory=list)
    payments: list[dict[str, str]] = field(default_factory=list)
    settlements: list[dict[str, str]] = field(default_factory=list)
    refunds: list[dict[str, str]] = field(default_factory=list)
    ground_truth: list[dict[str, str]] = field(default_factory=list)


def allocate_counts(total: int) -> dict[str, int]:
    raw = [(label, total * fraction) for label, fraction in ANOMALY_FRACTIONS]
    counts = {label: int(value) for label, value in raw}
    remainder = total - sum(counts.values())
    ordered = sorted(raw, key=lambda item: item[1] - int(item[1]), reverse=True)
    for index in range(remainder):
        counts[ordered[index % len(ordered)][0]] += 1
    return counts


def money_text(value: Decimal | None) -> str:
    if value is None:
        return ""
    return f"{round_money(value):.2f}"


def date_text(value: date) -> str:
    return value.isoformat()


def build_transaction_row(
    rng: random.Random,
    index: int,
    label: str,
    used_amounts: set[Decimal],
    dataset: GeneratedDataset,
) -> None:
    order_id = f"ORD-{index:05d}"
    payment_id = f"PAY-{index:05d}"
    settlement_id = f"SETL-{index:05d}"
    refund_id = f"REF-{index:05d}"
    customer_id = f"CUST-{rng.randint(1, 40):03d}"
    customer_name = CUSTOMERS[rng.randint(0, len(CUSTOMERS) - 1)]
    currency = "INR"

    amount = round_money(Decimal(rng.randint(AMOUNT_MIN, AMOUNT_MAX)))
    while amount in used_amounts:
        amount = round_money(Decimal(rng.randint(AMOUNT_MIN, AMOUNT_MAX)))
    used_amounts.add(amount)

    order_date = BASE_DATE + timedelta(days=rng.randint(0, 45))
    payment_date = order_date + timedelta(days=rng.randint(0, 1))
    settlement_date = payment_date + timedelta(days=rng.randint(1, 2))

    fee = expected_fee(amount)
    tax = expected_tax(fee)

    refund_amount: Decimal | None = None
    if label == "REFUND_NOT_SETTLED":
        refund_amount = round_money(amount * Decimal(str(round(rng.uniform(0.05, 0.25), 4))))
    elif label in ("CLEAN", "DATE_MISMATCH") and rng.random() < REFUND_RATE:
        refund_amount = round_money(amount * Decimal(str(round(rng.uniform(0.05, 0.25), 4))))

    gross = amount
    net_fee = fee
    net_tax = tax
    settled_refund = Decimal("0") if refund_amount is None or label == "REFUND_NOT_SETTLED" else refund_amount

    if label == "AMOUNT_MISMATCH":
        delta = Decimal(rng.randint(50, 500)) * rng.choice([1, -1])
        gross = round_money(amount + delta)
        net_fee = expected_fee(gross)
        net_tax = expected_tax(net_fee)
    elif label == "FEE_MISMATCH":
        net_fee = fee + Decimal(rng.randint(10, 100))
        net_tax = expected_tax(net_fee)
    elif label == "TAX_MISMATCH":
        net_tax = tax + Decimal(rng.randint(10, 100))
    elif label == "DATE_MISMATCH":
        settlement_date = payment_date + timedelta(days=rng.randint(10, 30))

    net = gross - net_fee - net_tax - settled_refund

    dataset.orders.append(
        {
            "order_id": order_id,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "order_amount": money_text(amount),
            "currency": currency,
            "order_date": date_text(order_date),
        }
    )

    source_records = [order_id]

    if label != "UNKNOWN_TRANSACTION":
        payment_row = {
            "payment_id": payment_id,
            "order_id": order_id,
            "customer_id": customer_id,
            "amount": money_text(amount),
            "currency": currency,
            "payment_date": date_text(payment_date),
            "payment_status": "captured",
        }
        dataset.payments.append(payment_row)
        if label == "DUPLICATE_TRANSACTION":
            dataset.payments.append(dict(payment_row))
        source_records.append(payment_id)

    if label != "MISSING_SETTLEMENT":
        dataset.settlements.append(
            {
                "settlement_id": settlement_id,
                "payment_id": payment_id,
                "settlement_date": date_text(settlement_date),
                "gross_amount": money_text(gross),
                "processing_fee": money_text(net_fee),
                "tax": money_text(net_tax),
                "net_amount": money_text(net),
                "currency": currency,
            }
        )
        source_records.append(settlement_id)

    if refund_amount is not None:
        refund_date = payment_date + timedelta(days=1)
        dataset.refunds.append(
            {
                "refund_id": refund_id,
                "payment_id": payment_id,
                "refund_amount": money_text(refund_amount),
                "refund_date": date_text(refund_date),
                "refund_status": "processed",
            }
        )
        source_records.append(refund_id)

    exception_type = ExceptionType.NONE if label == "CLEAN" else ExceptionType(label)
    if label == "UNKNOWN_TRANSACTION":
        transaction_id = settlement_id
        expected_settlement = ""
        actual_settlement = money_text(net)
        expected_variance = ""
    else:
        transaction_id = payment_id
        actual_settlement = "" if label == "MISSING_SETTLEMENT" else money_text(net)
        if label == "MISSING_SETTLEMENT":
            expected_settlement = ""
            expected_variance = ""
        else:
            expected_net = amount - fee - tax - (refund_amount if refund_amount is not None else Decimal("0"))
            expected_settlement = money_text(expected_net)
            expected_variance = money_text(expected_net - net)

    dataset.ground_truth.append(
        {
            "transaction_id": transaction_id,
            "expected_status": "MATCHED" if exception_type == ExceptionType.NONE else "EXCEPTION",
            "exception_type": exception_type.value,
            "expected_settlement": expected_settlement,
            "actual_settlement": actual_settlement,
            "expected_variance": expected_variance,
            "source_records": "|".join(source_records),
        }
    )


def generate_dataset(records: int, seed: int) -> GeneratedDataset:
    rng = random.Random(seed)
    counts = allocate_counts(records)
    labels: list[str] = []
    for label, count in counts.items():
        labels.extend([label] * count)
    rng.shuffle(labels)

    dataset = GeneratedDataset()
    used_amounts: set[Decimal] = set()
    for index, label in enumerate(labels, start=1):
        build_transaction_row(rng, index, label, used_amounts, dataset)
    return dataset


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_dataset(dataset: GeneratedDataset, generated_dir: Path, ground_truth_dir: Path) -> None:
    write_csv(generated_dir / "orders.csv", ORDER_FIELDS, dataset.orders)
    write_csv(generated_dir / "payments.csv", PAYMENT_FIELDS, dataset.payments)
    write_csv(generated_dir / "settlements.csv", SETTLEMENT_FIELDS, dataset.settlements)
    write_csv(generated_dir / "refunds.csv", REFUND_FIELDS, dataset.refunds)
    write_csv(ground_truth_dir / "ground_truth.csv", GROUND_TRUTH_FIELDS, dataset.ground_truth)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic reconciliation data with ground truth.")
    parser.add_argument("--records", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--generated-dir", type=Path, default=BACKEND_DIR / "data" / "generated")
    parser.add_argument("--ground-truth-dir", type=Path, default=BACKEND_DIR / "data" / "ground_truth")
    args = parser.parse_args()

    dataset = generate_dataset(args.records, args.seed)
    write_dataset(dataset, args.generated_dir, args.ground_truth_dir)

    injected = {}
    for row in dataset.ground_truth:
        injected[row["exception_type"]] = injected.get(row["exception_type"], 0) + 1

    print("DATA GENERATION COMPLETE")
    print(f"Records:              {args.records}")
    print(f"Seed:                 {args.seed}")
    print(f"Orders:               {len(dataset.orders)}")
    print(f"Payments:             {len(dataset.payments)}")
    print(f"Settlements:          {len(dataset.settlements)}")
    print(f"Refunds:              {len(dataset.refunds)}")
    print("Injected anomalies:")
    for exception_type in ExceptionType:
        if exception_type == ExceptionType.NONE:
            continue
        print(f"  {exception_type.value:<24}{injected.get(exception_type.value, 0)}")
    print(f"Generated dir:        {args.generated_dir}")
    print(f"Ground truth file:    {args.ground_truth_dir / 'ground_truth.csv'}")


if __name__ == "__main__":
    main()
