from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.transaction import TransactionResult


class ReconciliationResultModel(BaseModel):
    transaction_id: str
    status: str
    confidence: float
    expected_amount: float
    actual_amount: float | None
    net_expected: float | None = None
    fee: float | None
    tax: float | None
    variance: float
    exception_type: str
    reason: str
    recommendation: str
    match_method: str
    related_records: list[str] = Field(default_factory=list)


class ServiceInfoModel(BaseModel):
    service: str
    version: str
    app_env: str
    endpoints: list[str]


class BatchModel(BaseModel):
    id: str
    name: str
    status: str
    orders_count: int
    payments_count: int
    settlements_count: int
    refunds_count: int
    has_ground_truth: bool
    elapsed_seconds: float | None = None
    created_at: datetime
    reconciled_at: datetime | None = None


class MetricsModel(BaseModel):
    batch_id: str
    status: str
    total_records: int = 0
    matched_records: int = 0
    exception_records: int = 0
    match_rate: float = 0.0
    matching_precision: float | None = None
    exception_recall: float | None = None
    false_match_rate: float | None = None
    total_expected_amount: float = 0.0
    reconciled_amount: float = 0.0
    unresolved_amount: float = 0.0
    elapsed_seconds: float = 0.0
    throughput_per_second: float = 0.0
    evaluated_against_ground_truth: bool = False


class ExceptionsPageModel(BaseModel):
    total: int
    items: list[ReconciliationResultModel] = Field(default_factory=list)


class ControllerQueryRequest(BaseModel):
    batch_id: str
    question: str = Field(min_length=1, max_length=1000)


class ControllerAnswerModel(BaseModel):
    kind: str
    answer: str
    confirmed_facts: list[str] = Field(default_factory=list)
    probable_explanations: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    key_figures: dict[str, str] = Field(default_factory=dict)
    cited_transactions: list[str] = Field(default_factory=list)
    source: str
