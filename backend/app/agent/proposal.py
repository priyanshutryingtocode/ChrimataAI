from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import prompts
from app.agent.investigation import build_evidence_pack
from app.agent.llm import get_gemini_client
from app.core.config import settings
from app.core.formatting import format_inr
from app.models.batch import ResolutionRecord, TransactionResultRow, utc_now
from app.reconciliation.exceptions import ExceptionType
from app.reconciliation.financial import (
    ALLOWED_KINDS,
    ProposalKind,
    default_proposal_kind,
    proposed_amount_for,
    validate_proposal_amount,
    validate_proposal_kind,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"
MAX_PROPOSAL_AMOUNT = Decimal("100000000")


class LLMProposalModel(BaseModel):
    proposal_kind: str
    rationale: str = Field(min_length=1)
    proposed_amount: float | None = None
    confidence: float | None = None


def create_proposal(db: Session, batch_id: str, transaction_id: str, use_llm: bool = True) -> ResolutionRecord | None:
    row = _get_exception_row(db, batch_id, transaction_id)
    if row is None:
        return None

    active = get_active_proposal(db, batch_id, transaction_id)
    if active is not None:
        return active

    evidence = build_evidence_pack(db, batch_id, transaction_id)
    if evidence is None:
        return None

    exception_type = ExceptionType(row.exception_type)
    variance = abs(row.variance or Decimal("0"))
    allowed = ALLOWED_KINDS[exception_type]

    chosen = None
    proposed_by = "deterministic_rules"
    if use_llm:
        chosen = _ask_gemini_proposal(evidence, allowed, exception_type, variance)
        if chosen is not None:
            kind_error = validate_proposal_kind(chosen["kind"], exception_type, variance)
            amount_error = (
                validate_proposal_amount(chosen["kind"], chosen["amount"], variance)
                if kind_error is None
                else "kind invalid"
            )
            if kind_error is not None or amount_error is not None:
                logger.warning(
                    "LLM proposal rejected by pipeline validation (%s | %s); using rules fallback",
                    kind_error,
                    amount_error,
                )
                chosen = None
            else:
                proposed_by = "gemini"

    if chosen is None:
        kind = default_proposal_kind(exception_type)
        chosen = {
            "kind": kind,
            "amount": proposed_amount_for(kind, variance),
            "rationale": _rules_rationale(kind, evidence, variance),
            "confidence": None,
            "proposed_by": "deterministic_rules",
        }

    amount = Decimal(str(chosen["amount"])).quantize(Decimal("0.01"))

    record = ResolutionRecord(
        id=uuid4().hex,
        batch_id=batch_id,
        transaction_id=row.transaction_id,
        exception_type=row.exception_type,
        proposal_kind=chosen["kind"].value,
        rationale=chosen["rationale"],
        evidence_snapshot=json.dumps(evidence, default=str),
        variance_amount=row.variance,
        proposed_amount=amount,
        approved_amount=None,
        reconciled_adjustment_amount=Decimal("0"),
        workflow_status="PROPOSED",
        financial_status="UNRESOLVED",
        proposed_by=proposed_by,
        audit_json=json.dumps(
            [
                {
                    "event": "PROPOSAL_CREATED",
                    "actor": proposed_by,
                    "timestamp": utc_now().isoformat(),
                    "previous_status": "OPEN",
                    "new_status": "PROPOSED",
                    "proposal_kind": chosen["kind"].value,
                    "proposed_amount": float(chosen["amount"]),
                    "financial_effect": 0,
                    "note": "",
                }
            ]
        ),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_active_proposal(db: Session, batch_id: str, transaction_id: str) -> ResolutionRecord | None:
    return db.scalar(
        select(ResolutionRecord).where(
            ResolutionRecord.batch_id == batch_id,
            ResolutionRecord.transaction_id == transaction_id,
            ResolutionRecord.workflow_status == "PROPOSED",
        )
    )


def _get_exception_row(db: Session, batch_id: str, transaction_id: str) -> TransactionResultRow | None:
    return db.scalar(
        select(TransactionResultRow).where(
            TransactionResultRow.batch_id == batch_id,
            TransactionResultRow.transaction_id == transaction_id.upper(),
            TransactionResultRow.status == "EXCEPTION",
        )
    )


def _ask_gemini_proposal(evidence: dict, allowed: frozenset[ProposalKind], exception_type: ExceptionType, variance: Decimal):
    try:
        client = get_gemini_client()
        if client is None:
            return None

        from google.genai import types

        model = settings.llm_model.strip() or DEFAULT_MODEL
        kind_names = [kind.value for kind in allowed]
        instruction = (
            f"{prompts.SYSTEM_RULES}\n\n"
            "You are proposing an operational resolution for one exception.\n"
            f"Allowed proposal kinds for {exception_type.value}: {kind_names}.\n"
            "Financial rules:\n"
            "- ADJUSTMENT amount must be greater than 0 and at most the outstanding variance.\n"
            "- MARK_AS_VALID amount must be 0 and is only for DATE_MISMATCH.\n"
            "- VENDOR_QUERY, LINK_RECORD and RETRY_RECONCILIATION never reconcile money; "
            "set proposed_amount to the outstanding variance (or 0 for MARK_AS_VALID).\n"
            "The rationale must cite concrete amounts from the evidence. Never invent amounts."
        )
        config = types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
            response_schema=LLMProposalModel,
        )
        contents = [
            instruction,
            f"Evidence JSON:\n{json.dumps(evidence, default=str)}",
            f"Outstanding variance: {variance}",
        ]
        response = client.models.generate_content(model=model, contents=contents, config=config)

        parsed: LLMProposalModel | None = getattr(response, "parsed", None)
        if parsed is None and getattr(response, "text", None):
            parsed = LLMProposalModel.model_validate_json(response.text)
        if parsed is None:
            return None

        try:
            kind = ProposalKind(parsed.proposal_kind.strip().upper())
        except ValueError:
            logger.warning("Gemini proposed unsupported kind %s; using rules fallback", parsed.proposal_kind)
            return None

        if validate_proposal_kind(kind, exception_type, variance) is not None:
            logger.warning("Gemini kind %s invalid for %s; using rules fallback", kind, exception_type)
            return None

        amount = proposed_amount_for(kind, variance)
        if parsed.proposed_amount is not None:
            try:
                candidate = Decimal(str(parsed.proposed_amount)).quantize(Decimal("0.01"))
            except InvalidOperation:
                return None
            if candidate > MAX_PROPOSAL_AMOUNT:
                return None
            if validate_proposal_amount(kind, candidate, variance) is None:
                amount = candidate

        if not parsed.rationale.strip():
            return None

        return {"kind": kind, "amount": amount, "rationale": parsed.rationale.strip(), "confidence": parsed.confidence}
    except Exception:
        logger.exception("Gemini proposal failed; using deterministic rules fallback")
        return None


def _rules_rationale(kind: ProposalKind, evidence: dict, variance: Decimal) -> str:
    exception = evidence["exception"]
    reason = exception.get("reason", "")
    if kind == ProposalKind.ADJUSTMENT:
        return (
            f"Book an adjustment of {format_inr(variance)}: this is the unexplained residual after "
            f"fee {format_inr(Decimal(exception['fee'] or '0'))} and tax {format_inr(Decimal(exception['tax'] or '0'))}. "
            f"Engine reason: {reason}"
        )
    if kind == ProposalKind.MARK_AS_VALID:
        return "Timing difference only; monetary variance is zero. Mark as valid after review."
    if kind == ProposalKind.LINK_RECORD:
        return f"Locate and link the missing source record. Engine reason: {reason}"
    if kind == ProposalKind.RETRY_RECONCILIATION:
        return "Re-run the deterministic reconciliation to confirm the current state before escalation."
    return f"Raise a vendor query for {format_inr(variance)} outstanding. Engine reason: {reason}"
