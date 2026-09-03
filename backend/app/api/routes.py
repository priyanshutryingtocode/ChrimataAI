from __future__ import annotations

import csv
import io
import json
import uuid
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    BatchModel,
    ControllerAnswerModel,
    ControllerQueryRequest,
    ExceptionsPageModel,
    MetricsModel,
    ProposalRequestModel,
    ReconciliationResultModel,
    ResolutionDecisionModel,
    ResolutionRecordModel,
    ServiceInfoModel,
    WorkflowMetricsModel,
)
from app.agent.controller import run_controller_query
from app.agent.investigation import build_evidence_pack
from app.agent.proposal import create_proposal as _create_proposal
from app.core.batchfiles import generated_dir as _generated_dir
from app.core.batchfiles import ground_truth_file as _ground_truth_file
from app.core.config import DATA_DIR, settings
from app.core.database import get_db
from app.core.resolutions import ResolutionError, decide_proposal, effective_states, workflow_metrics
from app.models.batch import Batch, ResolutionRecord, TransactionResultRow, utc_now
from app.reconciliation.engine import run_reconciliation
from app.reconciliation.exceptions import ExceptionType
from app.reconciliation.metrics import evaluate
from app.reconciliation.normalize import load_ground_truth, load_source_data

router = APIRouter()

REQUIRED_COLUMNS: dict[str, list[str]] = {
    "orders": ["order_id", "customer_id", "customer_name", "order_amount", "currency", "order_date"],
    "payments": ["payment_id", "order_id", "customer_id", "amount", "currency", "payment_date", "payment_status"],
    "settlements": [
        "settlement_id",
        "payment_id",
        "settlement_date",
        "gross_amount",
        "processing_fee",
        "tax",
        "net_amount",
        "currency",
    ],
    "refunds": ["refund_id", "payment_id", "refund_amount", "refund_date", "refund_status"],
}


@router.get("/", response_model=ServiceInfoModel)
def service_info() -> ServiceInfoModel:
    return ServiceInfoModel(
        service="AI Finance Controller",
        version="0.5.0",
        app_env=settings.app_env,
        endpoints=[
            "/",
            "/health",
            "/api/batches",
            "/api/batches/upload",
            "/api/batches/{batch_id}",
            "/api/batches/{batch_id}/reconcile",
            "/api/batches/{batch_id}/metrics",
            "/api/batches/{batch_id}/results",
            "/api/batches/{batch_id}/exceptions",
            "/api/batches/{batch_id}/exceptions/{transaction_id}/evidence",
            "/api/batches/{batch_id}/exceptions/{transaction_id}/proposal",
            "/api/batches/{batch_id}/exceptions/{transaction_id}/resolution",
            "/api/batches/{batch_id}/resolutions",
            "/api/controller/query",
        ],
    )


@router.get("/health")
def health() -> dict:
    from sqlalchemy import text

    from app.core.database import engine

    db_status = "up"
    detail = None
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = "down"
        detail = str(exc)[:300]

    payload: dict[str, str | None] = {"status": "ok" if db_status == "up" else "degraded", "db": db_status}
    if detail:
        payload["detail"] = detail

    if db_status == "down":
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content=payload)
    return payload


@router.post("/api/controller/query", response_model=ControllerAnswerModel)
def controller_query(payload: ControllerQueryRequest, db: Session = Depends(get_db)) -> ControllerAnswerModel:
    answer = run_controller_query(db, payload.batch_id.strip(), payload.question.strip())
    if answer is None:
        batch = db.get(Batch, payload.batch_id.strip())
        if batch is None:
            raise HTTPException(status_code=404, detail=f"Batch {payload.batch_id} not found")
        if batch.status != "RECONCILED":
            raise HTTPException(
                status_code=409,
                detail=f"Batch {payload.batch_id} has not been reconciled yet",
            )
        raise HTTPException(status_code=500, detail="Query could not be processed")
    return ControllerAnswerModel(
        kind=answer.kind,
        answer=answer.answer,
        confirmed_facts=answer.confirmed_facts,
        probable_explanations=answer.probable_explanations,
        recommendations=answer.recommendations,
        key_figures=answer.key_figures,
        cited_transactions=answer.cited_transactions,
        source=answer.source,
    )


def _save_upload(upload: UploadFile, destination: Path, required_columns: list[str]) -> int:
    raw = upload.file.read().decode("utf-8-sig")
    reader = csv.reader(io.StringIO(raw))
    header = next(reader, None)
    if header is None:
        raise HTTPException(status_code=422, detail=f"{upload.filename}: file is empty")
    normalized = [column.strip().lower() for column in header]
    if required_columns and normalized != required_columns:
        raise HTTPException(
            status_code=422,
            detail=f"{upload.filename}: expected columns {required_columns}, got {normalized}",
        )
    row_count = sum(1 for row in reader if any(cell.strip() for cell in row))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(raw, encoding="utf-8")
    return row_count


def _to_batch_model(batch: Batch) -> BatchModel:
    return BatchModel(
        id=batch.id,
        name=batch.name,
        status=batch.status,
        orders_count=batch.orders_count,
        payments_count=batch.payments_count,
        settlements_count=batch.settlements_count,
        refunds_count=batch.refunds_count,
        has_ground_truth=batch.has_ground_truth,
        elapsed_seconds=batch.elapsed_seconds,
        created_at=batch.created_at,
        reconciled_at=batch.reconciled_at,
    )


def _get_batch_or_404(db: Session, batch_id: str) -> Batch:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")
    return batch


@router.post("/api/batches/upload", response_model=BatchModel)
def upload_batch(
    payments: UploadFile = File(...),
    settlements: UploadFile = File(...),
    orders: UploadFile | None = File(None),
    refunds: UploadFile | None = File(None),
    ground_truth: UploadFile | None = File(None),
    name: str = Form(""),
    db: Session = Depends(get_db),
) -> BatchModel:
    batch_id = uuid.uuid4().hex
    generated_dir = _generated_dir(batch_id)

    uploads: dict[str, tuple[UploadFile, list[str]]] = {
        "orders": (orders, REQUIRED_COLUMNS["orders"]),
        "payments": (payments, REQUIRED_COLUMNS["payments"]),
        "settlements": (settlements, REQUIRED_COLUMNS["settlements"]),
        "refunds": (refunds, REQUIRED_COLUMNS["refunds"]),
    }
    counts: dict[str, int] = {}
    for key, (upload, columns) in uploads.items():
        if upload is None or not upload.filename:
            continue
        counts[key] = _save_upload(upload, generated_dir / f"{key}.csv", columns)

    has_ground_truth = False
    if ground_truth is not None and ground_truth.filename:
        _save_upload(ground_truth, _ground_truth_file(batch_id), [])
        has_ground_truth = True

    batch = Batch(
        id=batch_id,
        name=name.strip(),
        status="UPLOADED",
        orders_count=counts.get("orders", 0),
        payments_count=counts.get("payments", 0),
        settlements_count=counts.get("settlements", 0),
        refunds_count=counts.get("refunds", 0),
        has_ground_truth=has_ground_truth,
        created_at=utc_now(),
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return _to_batch_model(batch)


@router.get("/api/batches", response_model=list[BatchModel])
def list_batches(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[BatchModel]:
    batches = db.scalars(
        select(Batch).order_by(Batch.created_at.desc()).limit(limit)
    ).all()
    return [_to_batch_model(batch) for batch in batches]


@router.get("/api/batches/{batch_id}", response_model=BatchModel)
def get_batch(batch_id: str, db: Session = Depends(get_db)) -> BatchModel:
    return _to_batch_model(_get_batch_or_404(db, batch_id))


def _result_row_from_result(batch_id: str, result) -> TransactionResultRow:
    variance = result.variance if result.variance is not None else Decimal("0")
    return TransactionResultRow(
        batch_id=batch_id,
        transaction_id=result.transaction_id,
        status=result.status,
        confidence=result.confidence,
        expected_amount=result.expected_amount,
        actual_amount=result.actual_amount,
        net_expected=result.net_expected,
        fee=result.fee,
        tax=result.tax,
        variance=variance,
        variance_abs_paise=int(round(abs(variance) * 100)),
        exception_type=result.exception_type.value,
        reason=result.reason,
        recommendation=result.recommendation,
        match_method=result.match_method,
        related_records="|".join(result.related_records),
    )


def _row_to_result_model(row: TransactionResultRow) -> ReconciliationResultModel:
    return ReconciliationResultModel(
        transaction_id=row.transaction_id,
        status=row.status,
        confidence=row.confidence,
        expected_amount=float(row.expected_amount) if row.expected_amount is not None else 0.0,
        actual_amount=float(row.actual_amount) if row.actual_amount is not None else None,
        net_expected=float(row.net_expected) if row.net_expected is not None else None,
        fee=float(row.fee) if row.fee is not None else None,
        tax=float(row.tax) if row.tax is not None else None,
        variance=float(row.variance) if row.variance is not None else 0.0,
        exception_type=row.exception_type,
        reason=row.reason,
        recommendation=row.recommendation,
        match_method=row.match_method,
        related_records=[item for item in row.related_records.split("|") if item],
    )


@router.post("/api/batches/{batch_id}/reconcile", response_model=BatchModel)
def reconcile_batch(batch_id: str, db: Session = Depends(get_db)) -> BatchModel:
    batch = _get_batch_or_404(db, batch_id)
    generated_dir = _generated_dir(batch_id)
    if not (generated_dir / "payments.csv").exists():
        raise HTTPException(status_code=409, detail=f"Batch {batch_id} has no stored files")

    source = load_source_data(generated_dir)
    report = run_reconciliation(source)

    db.execute(delete(TransactionResultRow).where(TransactionResultRow.batch_id == batch_id))
    for result in report.results:
        db.add(_result_row_from_result(batch_id, result))

    ground_truth_path = _ground_truth_file(batch_id)
    if ground_truth_path.exists():
        evaluation = evaluate(report, load_ground_truth(ground_truth_path))
        batch.evaluation_json = json.dumps(_evaluation_to_dict(evaluation))

    batch.status = "RECONCILED"
    batch.orders_count = len(source.orders)
    batch.payments_count = len(source.payments)
    batch.settlements_count = len(source.settlements)
    batch.refunds_count = len(source.refunds)
    batch.elapsed_seconds = report.elapsed_seconds
    batch.reconciled_at = utc_now()
    db.commit()
    db.refresh(batch)
    return _to_batch_model(batch)


def _evaluation_to_dict(evaluation) -> dict:
    predicted_matches = evaluation.correct_matches + evaluation.false_matches
    precision = evaluation.matching_precision if predicted_matches else None
    false_match_rate = evaluation.false_match_rate if predicted_matches else None
    recall = evaluation.exception_recall if evaluation.actual_exceptions else None
    return {
        "total_records": evaluation.total_records,
        "matched_records": evaluation.matched_records,
        "exception_records": evaluation.exception_records,
        "correct_matches": evaluation.correct_matches,
        "false_matches": evaluation.false_matches,
        "false_alarms": evaluation.false_alarms,
        "missed_exceptions": evaluation.missed_exceptions,
        "detected_exceptions": evaluation.detected_exceptions,
        "actual_exceptions": evaluation.actual_exceptions,
        "match_rate": evaluation.match_rate,
        "matching_precision": precision,
        "exception_recall": recall,
        "false_match_rate": false_match_rate,
        "total_expected_amount": float(evaluation.total_expected_amount),
        "reconciled_amount": float(evaluation.reconciled_amount),
        "unresolved_amount": float(evaluation.unresolved_amount),
        "elapsed_seconds": evaluation.elapsed_seconds,
        "throughput_per_second": evaluation.throughput_per_second,
    }


@router.get("/api/batches/{batch_id}/metrics", response_model=MetricsModel)
def get_metrics(batch_id: str, db: Session = Depends(get_db)) -> MetricsModel:
    batch = _get_batch_or_404(db, batch_id)
    if batch.status != "RECONCILED":
        raise HTTPException(status_code=409, detail=f"Batch {batch_id} has not been reconciled")

    payload = dict[str, object](
        batch_id=batch_id,
        status=batch.status,
        elapsed_seconds=batch.elapsed_seconds or 0.0,
        evaluated_against_ground_truth=False,
    )

    if batch.evaluation_json:
        stored = json.loads(batch.evaluation_json)
        payload.update(stored)
        payload["evaluated_against_ground_truth"] = True
    else:
        rows = db.scalars(select(TransactionResultRow).where(TransactionResultRow.batch_id == batch_id)).all()
        total = len(rows)
        matched_rows = [row for row in rows if row.status == "MATCHED"]
        total_expected = sum(
            (row.expected_amount or Decimal("0") for row in rows), Decimal("0")
        )
        reconciled = sum(
            (row.expected_amount or Decimal("0") for row in matched_rows), Decimal("0")
        )
        elapsed = max(batch.elapsed_seconds or 0.0, 1e-9)
        payload.update(
            {
                "total_records": total,
                "matched_records": len(matched_rows),
                "exception_records": total - len(matched_rows),
                "match_rate": len(matched_rows) / total if total else 0.0,
                "total_expected_amount": float(total_expected),
                "reconciled_amount": float(reconciled),
                "unresolved_amount": float(total_expected - reconciled),
                "throughput_per_second": total / elapsed,
            }
        )

    return MetricsModel(**payload, workflow=WorkflowMetricsModel(**workflow_metrics(db, batch_id)))


@router.get("/api/batches/{batch_id}/results", response_model=ExceptionsPageModel)
def get_results(
    batch_id: str,
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ExceptionsPageModel:
    _get_batch_or_404(db, batch_id)

    filters = [TransactionResultRow.batch_id == batch_id]
    if status is not None:
        normalized = status.strip().upper()
        if normalized not in ("MATCHED", "EXCEPTION"):
            raise HTTPException(status_code=422, detail=f"status must be MATCHED or EXCEPTION, got: {status}")
        filters.append(TransactionResultRow.status == normalized)

    base_query = select(TransactionResultRow).where(*filters)
    total = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0
    rows = db.scalars(
        base_query.order_by(
            TransactionResultRow.variance_abs_paise.desc(),
            TransactionResultRow.status.desc(),
            TransactionResultRow.transaction_id.asc(),
        )
        .offset(offset)
        .limit(limit)
    ).all()

    return ExceptionsPageModel(total=total, items=_attach_resolutions(db, batch_id, rows))


@router.get("/api/batches/{batch_id}/exceptions", response_model=ExceptionsPageModel)
def get_exceptions(
    batch_id: str,
    exception_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ExceptionsPageModel:
    _get_batch_or_404(db, batch_id)

    filters = [TransactionResultRow.batch_id == batch_id, TransactionResultRow.status == "EXCEPTION"]
    if exception_type is not None:
        try:
            ExceptionType(exception_type.strip().upper())
        except ValueError as error:
            raise HTTPException(status_code=422, detail=f"Unknown exception type: {exception_type}") from error
        filters.append(TransactionResultRow.exception_type == exception_type.strip().upper())

    base_query = select(TransactionResultRow).where(*filters)
    total = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0
    rows = db.scalars(
        base_query.order_by(TransactionResultRow.variance_abs_paise.desc(), TransactionResultRow.transaction_id.asc())
        .offset(offset)
        .limit(limit)
    ).all()

    return ExceptionsPageModel(total=total, items=_attach_resolutions(db, batch_id, rows))


def _attach_resolutions(db: Session, batch_id: str, rows) -> list[ReconciliationResultModel]:
    states = effective_states(db, batch_id)
    items = [_row_to_result_model(row) for row in rows]
    for item in items:
        state = states.get(item.transaction_id)
        if state is not None:
            item.resolution = state
    return items


def _resolution_to_model(record: ResolutionRecord) -> ResolutionRecordModel:
    return ResolutionRecordModel(
        id=record.id,
        batch_id=record.batch_id,
        transaction_id=record.transaction_id,
        exception_type=record.exception_type,
        proposal_kind=record.proposal_kind,
        rationale=record.rationale,
        evidence_snapshot=json.loads(record.evidence_snapshot or "{}"),
        variance_amount=float(record.variance_amount) if record.variance_amount is not None else None,
        proposed_amount=float(record.proposed_amount) if record.proposed_amount is not None else None,
        approved_amount=float(record.approved_amount) if record.approved_amount is not None else None,
        reconciled_adjustment_amount=(
            float(record.reconciled_adjustment_amount) if record.reconciled_adjustment_amount is not None else None
        ),
        workflow_status=record.workflow_status,
        financial_status=record.financial_status,
        proposed_by=record.proposed_by,
        approved_by=record.approved_by,
        human_note=record.human_note,
        audit=json.loads(record.audit_json or "[]"),
        created_at=record.created_at,
        updated_at=record.updated_at,
        resolved_at=record.resolved_at,
    )


@router.get("/api/batches/{batch_id}/exceptions/{transaction_id}/evidence")
def get_evidence(batch_id: str, transaction_id: str, db: Session = Depends(get_db)) -> dict:
    _get_batch_or_404(db, batch_id)
    normalized = transaction_id.strip().upper()
    record = db.scalar(
        select(ResolutionRecord)
        .where(ResolutionRecord.batch_id == batch_id)
        .where(ResolutionRecord.transaction_id == normalized)
        .order_by(ResolutionRecord.created_at.desc())
        .limit(1)
    )
    if record is not None:
        return {
            "source": "snapshot",
            "proposal_id": record.id,
            "captured_at": record.created_at.isoformat(),
            "evidence": json.loads(record.evidence_snapshot or "{}"),
        }
    evidence = build_evidence_pack(db, batch_id, normalized)
    if evidence is None:
        raise HTTPException(status_code=404, detail=f"Exception {normalized} not found in batch {batch_id}")
    return {"source": "live", "proposal_id": None, "captured_at": utc_now().isoformat(), "evidence": evidence}


@router.post("/api/batches/{batch_id}/exceptions/{transaction_id}/proposal", response_model=ResolutionRecordModel)
def create_exception_proposal(
    batch_id: str,
    transaction_id: str,
    payload: ProposalRequestModel | None = None,
    db: Session = Depends(get_db),
) -> ResolutionRecordModel:
    batch = _get_batch_or_404(db, batch_id)
    if batch.status != "RECONCILED":
        raise HTTPException(status_code=409, detail=f"Batch {batch_id} has not been reconciled")

    from app.agent.proposal import get_active_proposal

    normalized = transaction_id.strip().upper()
    if get_active_proposal(db, batch_id, normalized) is not None:
        raise HTTPException(status_code=409, detail=f"Exception {normalized} already has an active proposal")

    use_llm = payload.use_llm if payload is not None else True
    record = _create_proposal(db, batch_id, normalized, use_llm=use_llm)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Exception {normalized} not found in batch {batch_id}")
    return _resolution_to_model(record)


@router.post("/api/batches/{batch_id}/exceptions/{transaction_id}/resolution", response_model=ResolutionRecordModel)
def decide_exception_resolution(
    batch_id: str,
    transaction_id: str,
    payload: ResolutionDecisionModel,
    db: Session = Depends(get_db),
) -> ResolutionRecordModel:
    _get_batch_or_404(db, batch_id)
    amount = (
        Decimal(str(payload.approved_amount)).quantize(Decimal("0.01"))
        if payload.approved_amount is not None
        else None
    )
    try:
        record = decide_proposal(
            db,
            batch_id,
            transaction_id,
            decision=payload.decision,
            approved_amount=amount,
            approved_by=payload.approved_by.strip() or "dashboard-user",
            note=payload.note.strip(),
        )
    except ResolutionError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    return _resolution_to_model(record)


@router.get("/api/batches/{batch_id}/resolutions", response_model=list[ResolutionRecordModel])
def list_resolutions(
    batch_id: str,
    status: str | None = Query(None),
    transaction_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[ResolutionRecordModel]:
    _get_batch_or_404(db, batch_id)
    filters = [ResolutionRecord.batch_id == batch_id]
    if status is not None:
        normalized = status.strip().upper()
        if normalized not in ("PROPOSED", "RESOLVED", "REJECTED"):
            raise HTTPException(status_code=422, detail=f"status must be PROPOSED, RESOLVED or REJECTED, got: {status}")
        filters.append(ResolutionRecord.workflow_status == normalized)
    if transaction_id is not None:
        filters.append(ResolutionRecord.transaction_id == transaction_id.strip().upper())
    records = db.scalars(
        select(ResolutionRecord)
        .where(*filters)
        .order_by(ResolutionRecord.created_at.desc())
        .limit(limit)
    ).all()
    return [_resolution_to_model(record) for record in records]
