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
    resolution: dict | None = None


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
    workflow: "WorkflowMetricsModel | None" = None


class WorkflowMetricsModel(BaseModel):
    total_exceptions: int = 0
    open_exceptions: int = 0
    proposed_exceptions: int = 0
    workflow_resolved_exceptions: int = 0
    rejected_proposals: int = 0
    workflow_resolution_rate: float = 0.0
    total_exception_amount: float = 0.0
    amount_proposed: float = 0.0
    amount_approved: float = 0.0
    amount_financially_reconciled: float = 0.0
    amount_outstanding: float = 0.0
    financial_resolution_rate: float = 0.0
    financially_reconciled_exceptions: int = 0


class ResolutionRecordModel(BaseModel):
    id: str
    batch_id: str
    transaction_id: str
    exception_type: str
    proposal_kind: str
    rationale: str
    evidence_snapshot: dict = Field(default_factory=dict)
    variance_amount: float | None = None
    proposed_amount: float | None = None
    approved_amount: float | None = None
    reconciled_adjustment_amount: float | None = None
    workflow_status: str
    financial_status: str
    proposed_by: str
    approved_by: str | None = None
    human_note: str = ""
    audit: list[dict] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None


class ProposalRequestModel(BaseModel):
    use_llm: bool = True


class ResolutionDecisionModel(BaseModel):
    decision: str
    approved_amount: float | None = None
    approved_by: str = "dashboard-user"
    note: str = ""


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
