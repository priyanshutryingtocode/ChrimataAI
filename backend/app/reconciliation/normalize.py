from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from app.models.transaction import Order, Payment, Refund, Settlement, SourceData


def normalize_id(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().upper()


def normalize_currency(value: object) -> str:
    text = normalize_id(value)
    return text or "INR"


def parse_money(value: object) -> Decimal | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().replace(",", "").replace("₹", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_date(value: object) -> date | None:
    if value is None or pd.isna(value):
        return None
    try:
        return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def load_orders(path: Path) -> list[Order]:
    frame = pd.read_csv(path, dtype=str)
    orders: list[Order] = []
    for _, row in frame.iterrows():
        orders.append(
            Order(
                order_id=normalize_id(row["order_id"]),
                customer_id=normalize_id(row["customer_id"]),
                customer_name=str(row.get("customer_name", "") or "").strip(),
                order_amount=parse_money(row["order_amount"]) or Decimal("0"),
                currency=normalize_currency(row.get("currency")),
                order_date=parse_date(row["order_date"]),
            )
        )
    return orders


def load_payments(path: Path) -> list[Payment]:
    frame = pd.read_csv(path, dtype=str)
    payments: list[Payment] = []
    for _, row in frame.iterrows():
        payments.append(
            Payment(
                payment_id=normalize_id(row["payment_id"]),
                order_id=normalize_id(row["order_id"]),
                customer_id=normalize_id(row["customer_id"]),
                amount=parse_money(row["amount"]) or Decimal("0"),
                currency=normalize_currency(row.get("currency")),
                payment_date=parse_date(row["payment_date"]),
                payment_status=str(row.get("payment_status", "") or "").strip().lower(),
            )
        )
    return payments


def load_settlements(path: Path) -> list[Settlement]:
    frame = pd.read_csv(path, dtype=str)
    settlements: list[Settlement] = []
    for _, row in frame.iterrows():
        settlements.append(
            Settlement(
                settlement_id=normalize_id(row["settlement_id"]),
                payment_id=normalize_id(row["payment_id"]),
                settlement_date=parse_date(row["settlement_date"]),
                gross_amount=parse_money(row["gross_amount"]) or Decimal("0"),
                processing_fee=parse_money(row["processing_fee"]) or Decimal("0"),
                tax=parse_money(row["tax"]) or Decimal("0"),
                net_amount=parse_money(row["net_amount"]) or Decimal("0"),
                currency=normalize_currency(row.get("currency")),
            )
        )
    return settlements


def load_refunds(path: Path) -> list[Refund]:
    frame = pd.read_csv(path, dtype=str)
    refunds: list[Refund] = []
    for _, row in frame.iterrows():
        refunds.append(
            Refund(
                refund_id=normalize_id(row["refund_id"]),
                payment_id=normalize_id(row["payment_id"]),
                refund_amount=parse_money(row["refund_amount"]) or Decimal("0"),
                refund_date=parse_date(row["refund_date"]),
                refund_status=str(row.get("refund_status", "") or "").strip().lower(),
            )
        )
    return refunds


def load_source_data(directory: Path) -> SourceData:
    return SourceData(
        orders=load_orders(directory / "orders.csv"),
        payments=load_payments(directory / "payments.csv"),
        settlements=load_settlements(directory / "settlements.csv"),
        refunds=load_refunds(directory / "refunds.csv"),
    )


def load_ground_truth(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str)
