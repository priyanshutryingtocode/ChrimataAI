from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent import prompts, tools
from app.core.config import settings
from app.core.formatting import format_inr

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"
MAX_MENTIONED_TRANSACTIONS = 5
TRANSACTION_ID_PATTERN = re.compile(r"\b(?:PAY|SETL|ORD|REF|TXN)-\d{1,6}\b", re.IGNORECASE)


class AnswerKind(str, Enum):
    FACTUAL = "FACTUAL"
    CALCULATED = "CALCULATED"
    EXPLANATION = "EXPLANATION"
    RECOMMENDATION = "RECOMMENDATION"
    NOT_FOUND = "NOT_FOUND"


class LLMAnswerModel(BaseModel):
    kind: AnswerKind = AnswerKind.FACTUAL
    answer: str = Field(min_length=1)
    confirmed_facts: list[str] = Field(default_factory=list)
    probable_explanations: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    cited_transaction_ids: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ControllerAnswer:
    kind: str
    answer: str
    confirmed_facts: list[str] = field(default_factory=list)
    probable_explanations: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    key_figures: dict[str, str] = field(default_factory=dict)
    cited_transactions: list[str] = field(default_factory=list)
    source: str = "deterministic_fallback"


def extract_transaction_ids(question: str) -> list[str]:
    matches = TRANSACTION_ID_PATTERN.findall(question or "")
    seen: list[str] = []
    for match in matches:
        normalized = match.upper()
        if normalized not in seen:
            seen.append(normalized)
    return seen


def run_controller_query(db: Session, batch_id: str, question: str) -> ControllerAnswer | None:
    pack = build_context_pack(db, batch_id, question)
    if pack is None:
        return None

    llm_answer = _ask_gemini(question, pack)
    if llm_answer is not None:
        return llm_answer
    return _fallback_answer(db, batch_id, question)


def build_context_pack(db: Session, batch_id: str, question: str) -> dict | None:
    facts = tools.get_batch_facts(db, batch_id)
    if facts is None:
        return None

    mentioned: list[dict] = []
    for transaction_id in extract_transaction_ids(question)[:MAX_MENTIONED_TRANSACTIONS]:
        detail = tools.find_transaction(db, batch_id, transaction_id)
        if detail is None:
            mentioned.append({"transaction_id": transaction_id, "found": False})
        else:
            entry = _detail_to_dict(detail)
            entry["found"] = True
            mentioned.append(entry)

    top_exceptions = [_detail_to_dict(detail) for detail in tools.list_top_exceptions(db, batch_id)]

    return {
        "batch": {
            "batch_id": facts.batch_id,
            "name": facts.batch_name,
            "status": facts.status,
        },
        "metrics": _facts_to_dict(facts),
        "exception_type_counts": tools.get_exception_type_distribution(db, batch_id),
        "top_exceptions_by_variance": top_exceptions,
        "mentioned_transactions": mentioned,
    }


def _facts_to_dict(facts: tools.BatchFacts) -> dict:
    return {
        "total_records": facts.total_records,
        "matched_records": facts.matched_records,
        "exception_records": facts.exception_records,
        "match_rate_percent": round(facts.match_rate * 100, 2),
        "total_expected_amount": str(facts.total_expected_amount),
        "reconciled_amount": str(facts.reconciled_amount),
        "unresolved_amount": str(facts.unresolved_amount),
        "throughput_per_second": round(facts.throughput_per_second, 1),
        "evaluated_against_ground_truth": facts.evaluated_against_ground_truth,
        "matching_precision": facts.matching_precision,
        "exception_recall": facts.exception_recall,
        "false_match_rate": facts.false_match_rate,
    }


def _detail_to_dict(detail: tools.TransactionDetail) -> dict:
    def money(value: Decimal | None) -> str | None:
        return None if value is None else format_inr(value)

    return {
        "transaction_id": detail.transaction_id,
        "status": detail.status,
        "confidence": detail.confidence,
        "expected_amount": money(detail.expected_amount),
        "actual_amount": money(detail.actual_amount),
        "fee": money(detail.fee),
        "tax": money(detail.tax),
        "variance": money(detail.variance),
        "exception_type": detail.exception_type,
        "reason": detail.reason,
        "recommendation": detail.recommendation,
        "match_method": detail.match_method,
        "related_records": detail.related_records,
    }


def _get_gemini_client():
    api_key = settings.llm_api_key.strip()
    if not api_key:
        return None
    from google import genai

    return genai.Client(api_key=api_key)


def _ask_gemini(question: str, context_pack: dict) -> ControllerAnswer | None:
    try:
        client = _get_gemini_client()
        if client is None:
            return None

        from google.genai import types

        model = settings.llm_model.strip() or DEFAULT_MODEL
        config = types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
            response_schema=LLMAnswerModel,
        )
        contents = [
            f"{prompts.SYSTEM_RULES}\n\n{prompts.EXPLANATION_HINT}",
            f"Context JSON:\n{json.dumps(context_pack)}",
            f"Question: {question}",
        ]
        response = client.models.generate_content(model=model, contents=contents, config=config)

        parsed: LLMAnswerModel | None = getattr(response, "parsed", None)
        if parsed is None and getattr(response, "text", None):
            parsed = LLMAnswerModel.model_validate_json(response.text)
        if parsed is None or not parsed.answer.strip():
            logger.warning("Gemini returned an empty answer; using deterministic fallback")
            return None

        return ControllerAnswer(
            kind=parsed.kind.value if isinstance(parsed.kind, AnswerKind) else str(parsed.kind),
            answer=parsed.answer,
            confirmed_facts=parsed.confirmed_facts,
            probable_explanations=parsed.probable_explanations,
            recommendations=parsed.recommendations,
            cited_transactions=_valid_citations(parsed.cited_transaction_ids, context_pack),
            source="gemini",
        )
    except Exception:
        logger.exception("Gemini call failed; falling back to deterministic answers")
        return None


def _valid_citations(candidates: list[str], context_pack: dict) -> list[str]:
    known = {item["transaction_id"] for item in context_pack["mentioned_transactions"] if item.get("found")}
    known.update(item["transaction_id"] for item in context_pack["top_exceptions_by_variance"])
    valid: list[str] = []
    for candidate in candidates:
        normalized = candidate.strip().upper()
        if normalized in known and normalized not in valid:
            valid.append(normalized)
    return valid


def _fallback_answer(db: Session, batch_id: str, question: str) -> ControllerAnswer:
    facts = tools.get_batch_facts(db, batch_id)
    assert facts is not None
    counts = tools.get_exception_type_distribution(db, batch_id)

    lowered = (question or "").lower()
    mentioned = extract_transaction_ids(question)

    if mentioned:
        return _explain_transaction(db, batch_id, mentioned[0], facts)
    if _mentions_any(lowered, ("unresolved amount", "unmatched amount", "money at risk")) or (
        "how much" in lowered and "unresolved" in lowered
    ):
        return ControllerAnswer(
            kind=AnswerKind.FACTUAL.value,
            answer=(
                f"The total unresolved amount for this batch is {format_inr(facts.unresolved_amount)} "
                f"across {facts.exception_records} exception records."
            ),
            key_figures={
                "Unresolved amount": format_inr(facts.unresolved_amount),
                "Exception records": str(facts.exception_records),
            },
            confirmed_facts=[
                f"{facts.exception_records} of {facts.total_records} records are unresolved exceptions.",
            ],
        )
    if "how many" in lowered and _mentions_any(lowered, ("unresolved", "unmatched", "exception")):
        return ControllerAnswer(
            kind=AnswerKind.FACTUAL.value,
            answer=(
                f"{facts.exception_records} transactions are unresolved out of {facts.total_records} processed "
                f"(match rate {facts.match_rate * 100:.2f}%)."
            ),
            key_figures={
                "Unresolved records": str(facts.exception_records),
                "Total records": str(facts.total_records),
                "Match rate": f"{facts.match_rate * 100:.2f}%",
            },
            confirmed_facts=[f"Match rate is {facts.match_rate * 100:.2f}%."],
        )
    if _mentions_any(lowered, ("how much money is currently reconciled", "reconciled amount", "matched amount")):
        return ControllerAnswer(
            kind=AnswerKind.CALCULATED.value,
            answer=(
                f"Reconciled amount is {format_inr(facts.reconciled_amount)} "
                f"({facts.matched_records} records), leaving {format_inr(facts.unresolved_amount)} unresolved."
            ),
            key_figures={
                "Reconciled amount": format_inr(facts.reconciled_amount),
                "Unresolved amount": format_inr(facts.unresolved_amount),
            },
        )
    if _mentions_any(lowered, ("percentage", "match rate", "%")) and _mentions_any(lowered, ("match",)):
        return ControllerAnswer(
            kind=AnswerKind.FACTUAL.value,
            answer=f"{facts.match_rate * 100:.2f}% of transactions were matched ({facts.matched_records}/{facts.total_records}).",
            key_figures={"Match rate": f"{facts.match_rate * 100:.2f}%"},
        )
    if "top" in lowered and _mentions_any(lowered, ("exception type", "exception types", "types")):
        limit = _parse_top_n(lowered)
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
        lines = [f"{index}. {name}: {count}" for index, (name, count) in enumerate(ranked, start=1)]
        return ControllerAnswer(
            kind=AnswerKind.FACTUAL.value,
            answer="Top exception types:\n" + "\n".join(lines),
            key_figures={name: str(count) for name, count in ranked},
        )
    if _mentions_any(lowered, ("largest", "biggest", "highest")) and "variance" in lowered:
        top = tools.list_top_exceptions(db, batch_id, limit=1)
        if top:
            detail = top[0]
            summary = _explain_transaction(db, batch_id, detail.transaction_id, facts)
            return summary
    return ControllerAnswer(
        kind=AnswerKind.FACTUAL.value,
        answer=(
            f"Batch summary: {facts.total_records} records processed, {facts.matched_records} matched, "
            f"{facts.exception_records} exceptions. Match rate {facts.match_rate * 100:.2f}%. "
            f"Reconciled {format_inr(facts.reconciled_amount)} of {format_inr(facts.total_expected_amount)}; "
            f"unresolved {format_inr(facts.unresolved_amount)}."
        ),
        key_figures={
            "Records": str(facts.total_records),
            "Matched": str(facts.matched_records),
            "Exceptions": str(facts.exception_records),
            "Unresolved amount": format_inr(facts.unresolved_amount),
        },
    )


def _explain_transaction(
    db: Session,
    batch_id: str,
    transaction_id: str,
    facts: tools.BatchFacts,
) -> ControllerAnswer:
    detail = tools.find_transaction(db, batch_id, transaction_id)
    if detail is None:
        return ControllerAnswer(
            kind=AnswerKind.NOT_FOUND.value,
            answer=(
                f"No transaction with ID {transaction_id} exists in this batch. "
                f"The batch contains {facts.total_records} reconciled records."
            ),
            cited_transactions=[],
        )

    lines = [
        f"{transaction_id} has status {detail.status}"
        + (f" with exception type {detail.exception_type}." if detail.status != "MATCHED" else "."),
        f"Engine reason: {detail.reason}",
    ]
    figures = {
        "Status": detail.status,
        "Expected amount": format_inr(detail.expected_amount or Decimal("0")),
        "Actual amount": format_inr(detail.actual_amount or Decimal("0")),
        "Variance": format_inr(detail.variance or Decimal("0")),
    }
    explanations: list[str] = []
    if detail.status == "EXCEPTION":
        explanations.append(
            "Probable cause based on the exception type and recorded amounts; verify against gateway reports before action."
        )
    return ControllerAnswer(
        kind=AnswerKind.EXPLANATION.value,
        answer="\n".join(lines),
        confirmed_facts=[f"Exception type: {detail.exception_type}", f"Engine reason: {detail.reason}"],
        probable_explanations=explanations,
        recommendations=[detail.recommendation] if detail.recommendation else [],
        key_figures=figures,
        cited_transactions=[transaction_id],
    )


def _mentions_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _parse_top_n(text: str) -> int:
    match = re.search(r"top\s+(\d+)", text)
    if match:
        return max(1, min(10, int(match.group(1))))
    word_numbers = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
    for word, value in word_numbers.items():
        if re.search(rf"top\s+{word}\b", text):
            return value
    return 3
