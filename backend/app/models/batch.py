from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, MoneyType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(20), default="UPLOADED")
    orders_count: Mapped[int] = mapped_column(Integer, default=0)
    payments_count: Mapped[int] = mapped_column(Integer, default=0)
    settlements_count: Mapped[int] = mapped_column(Integer, default=0)
    refunds_count: Mapped[int] = mapped_column(Integer, default=0)
    has_ground_truth: Mapped[bool] = mapped_column(default=False)
    elapsed_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    evaluation_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    reconciled_at: Mapped[datetime | None] = mapped_column(nullable=True)


class TransactionResultRow(Base):
    __tablename__ = "transaction_results"
    __table_args__ = (UniqueConstraint("batch_id", "transaction_id", name="uq_batch_transaction"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id", ondelete="CASCADE"), index=True)
    transaction_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float)
    expected_amount: Mapped[object] = mapped_column(MoneyType, nullable=True)
    actual_amount: Mapped[object] = mapped_column(MoneyType, nullable=True)
    fee: Mapped[object] = mapped_column(MoneyType, nullable=True)
    tax: Mapped[object] = mapped_column(MoneyType, nullable=True)
    variance: Mapped[object] = mapped_column(MoneyType, nullable=True)
    variance_abs_paise: Mapped[int] = mapped_column(Integer, default=0, index=True)
    exception_type: Mapped[str] = mapped_column(String(40), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    recommendation: Mapped[str] = mapped_column(Text, default="")
    match_method: Mapped[str] = mapped_column(String(40), default="payment_id")
    related_records: Mapped[str] = mapped_column(Text, default="")
