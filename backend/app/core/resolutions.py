from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.batchfiles import generated_dir
from app.models.batch import ResolutionRecord, TransactionResultRow, utc_now
from app.reconciliation.engine import run_reconciliation
from app.reconciliation.exceptions import ExceptionType
from app.reconciliation.financial import ProposalKind, apply_financial_effect, validate_proposal_amount
from app.reconciliation.normalize import load_source_data


class ResolutionError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


def decide_proposal(
    db: Session,
    batch_id: str,
    transaction_id: str,
    decision: str,
    approved_amount: Decimal | None,
    approved_by: str,
    note: str,
) -> ResolutionRecord:
    record = db.scalar(
        select(ResolutionRecord).where(
            ResolutionRecord.batch_id == batch_id,
            ResolutionRecord.transaction_id == transaction_id.upper(),
            ResolutionRecord.workflow_status == "PROPOSED",
        )
    )
    if record is None:
        raise ResolutionError(f"No active proposal for exception {transaction_id}")

    kind = ProposalKind(record.proposal_kind)
    variance = abs(record.variance_amount or Decimal("0"))
    decision_normalized = decision.strip().upper()
    if decision_normalized not in ("APPROVED", "REJECTED"):
        raise ResolutionError("decision must be APPROVED or REJECTED", status_code=422)

    if decision_normalized == "REJECTED":
        record.workflow_status = "REJECTED"
        record.approved_by = approved_by
        record.human_note = note
        record.updated_at = utc_now()
        _append_audit(
            record,
            event="PROPOSAL_REJECTED",
            actor=approved_by,
            previous_status="PROPOSED",
            new_status="REJECTED",
            approved_amount=None,
            financial_effect=Decimal("0"),
            note=note,
        )
        db.commit()
        db.refresh(record)
        return record

    amount = approved_amount if approved_amount is not None else (record.proposed_amount or Decimal("0"))
    amount = Decimal(amount).quantize(Decimal("0.01"))
    amount_error = validate_proposal_amount(kind, amount, variance)
    if amount_error is not None:
        raise ResolutionError(amount_error, status_code=422)

    effect = apply_financial_effect(kind, amount, variance, record.financial_status)

    record.workflow_status = "RESOLVED"
    record.financial_status = effect.financial_status
    record.approved_amount = amount
    record.reconciled_adjustment_amount = effect.reconciled_adjustment_amount
    record.approved_by = approved_by
    record.human_note = note
    record.resolved_at = utc_now()
    record.updated_at = utc_now()

    _append_audit(
        record,
        event="PROPOSAL_APPROVED",
        actor=approved_by,
        previous_status="PROPOSED",
        new_status="RESOLVED",
        approved_amount=amount,
        financial_effect=effect.reconciled_adjustment_amount,
        note=note,
    )

    if kind == ProposalKind.RETRY_RECONCILIATION:
        summary = _execute_retry(db, batch_id, record.transaction_id)
        _append_audit(
            record,
            event="RETRY_RECONCILIATION_EXECUTED",
            actor="engine",
            previous_status="RESOLVED",
            new_status=record.financial_status,
            approved_amount=amount,
            financial_effect=effect.reconciled_adjustment_amount,
            note=json.dumps(summary),
        )

    db.commit()
    db.refresh(record)
    return record


def effective_states(db: Session, batch_id: str) -> dict[str, dict[str, str]]:
    records = db.scalars(
        select(ResolutionRecord)
        .where(ResolutionRecord.batch_id == batch_id)
        .order_by(ResolutionRecord.created_at.asc())
    ).all()
    states: dict[str, dict[str, str]] = {}
    for record in records:
        workflow = "OPEN" if record.workflow_status == "REJECTED" else record.workflow_status
        financial = record.financial_status if workflow in ("PROPOSED", "RESOLVED") else "UNRESOLVED"
        states[record.transaction_id] = {
            "workflow_status": workflow,
            "financial_status": financial,
            "proposal_id": record.id,
            "proposal_kind": record.proposal_kind,
        }
    return states


def workflow_metrics(db: Session, batch_id: str) -> dict:
    exception_rows = db.scalars(
        select(TransactionResultRow)
        .where(TransactionResultRow.batch_id == batch_id)
        .where(TransactionResultRow.status == "EXCEPTION")
    ).all()
    records = db.scalars(
        select(ResolutionRecord).where(ResolutionRecord.batch_id == batch_id)
    ).all()

    total_exceptions = len(exception_rows)
    exception_amount = sum((abs(row.variance or Decimal("0")) for row in exception_rows), Decimal("0"))

    states = effective_states(db, batch_id)
    open_count = sum(1 for state in states.values() if state["workflow_status"] == "OPEN")
    proposed_count = sum(1 for state in states.values() if state["workflow_status"] == "PROPOSED")
    resolved_count = sum(1 for state in states.values() if state["workflow_status"] == "RESOLVED")
    rejected_count = sum(1 for record in records if record.workflow_status == "REJECTED")

    amount_proposed = sum(
        (record.proposed_amount or Decimal("0") for record in records if record.workflow_status != "REJECTED"),
        Decimal("0"),
    )
    amount_approved = sum(
        (record.approved_amount or Decimal("0") for record in records if record.workflow_status == "RESOLVED"),
        Decimal("0"),
    )
    amount_reconciled = sum(
        (record.reconciled_adjustment_amount or Decimal("0") for record in records),
        Decimal("0"),
    )
    amount_outstanding = exception_amount - amount_reconciled
    financial_resolved_count = sum(
        1 for state in states.values() if state["financial_status"] == "RECONCILED"
    )

    return {
        "total_exceptions": total_exceptions,
        "open_exceptions": open_count,
        "proposed_exceptions": proposed_count,
        "workflow_resolved_exceptions": resolved_count,
        "rejected_proposals": rejected_count,
        "workflow_resolution_rate": resolved_count / total_exceptions if total_exceptions else 0.0,
        "total_exception_amount": float(exception_amount),
        "amount_proposed": float(amount_proposed),
        "amount_approved": float(amount_approved),
        "amount_financially_reconciled": float(amount_reconciled),
        "amount_outstanding": float(amount_outstanding),
        "financial_resolution_rate": float(amount_reconciled / exception_amount) if exception_amount else 0.0,
        "financially_reconciled_exceptions": financial_resolved_count,
    }


def _execute_retry(db: Session, batch_id: str, transaction_id: str) -> dict:
    source = load_source_data(generated_dir(batch_id))
    report = run_reconciliation(source)
    row = next((r for r in report.results if r.transaction_id == transaction_id.upper()), None)
    return {
        "records_processed": report.total_records,
        "transaction_id": transaction_id.upper(),
        "status_after_retry": row.status if row else "NOT_FOUND",
        "exception_type_after_retry": row.exception_type.value if row else None,
        "note": "Deterministic re-run completed; persisted engine metrics are unchanged.",
    }


def _append_audit(
    record: ResolutionRecord,
    event: str,
    actor: str,
    previous_status: str,
    new_status: str,
    approved_amount: Decimal | None,
    financial_effect: Decimal,
    note: str,
) -> None:
    events = json.loads(record.audit_json or "[]")
    events.append(
        {
            "event": event,
            "actor": actor,
            "timestamp": utc_now().isoformat(),
            "previous_status": previous_status,
            "new_status": new_status,
            "proposal_id": record.id,
            "exception_id": record.transaction_id,
            "proposal_kind": record.proposal_kind,
            "approved_amount": float(approved_amount) if approved_amount is not None else None,
            "financial_effect": float(financial_effect),
            "note": note,
        }
    )
    record.audit_json = json.dumps(events)
