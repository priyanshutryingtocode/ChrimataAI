from __future__ import annotations

from dataclasses import dataclass, field

from app.models.transaction import Order, Payment, Refund, Settlement
from app.reconciliation.rules import (
    EXACT_MATCH_CONFIDENCE,
    SECONDARY_AMOUNT_WINDOW,
    SECONDARY_DATE_WINDOW_DAYS,
    SECONDARY_MATCH_CONFIDENCE,
    is_valid_refund_status,
)


@dataclass(frozen=True)
class PaymentMatch:
    payment: Payment
    duplicate_payment_rows: int
    order: Order | None
    settlements: list[Settlement] = field(default_factory=list)
    valid_refunds: list[Refund] = field(default_factory=list)
    match_method: str = "payment_id"
    confidence: float = EXACT_MATCH_CONFIDENCE


@dataclass(frozen=True)
class MatchOutput:
    payment_matches: list[PaymentMatch]
    orphan_settlements: list[Settlement]


def build_matches(
    payments: list[Payment],
    settlements: list[Settlement],
    refunds: list[Refund],
    orders: list[Order],
) -> MatchOutput:
    payments_by_id: dict[str, list[Payment]] = {}
    for payment in payments:
        payments_by_id.setdefault(payment.payment_id, []).append(payment)

    direct_settlements: dict[str, list[Settlement]] = {
        payment_id: [] for payment_id in payments_by_id
    }
    orphan_candidates: list[Settlement] = []
    for settlement in settlements:
        if settlement.payment_id in direct_settlements:
            direct_settlements[settlement.payment_id].append(settlement)
        else:
            orphan_candidates.append(settlement)

    orders_by_id = {order.order_id: order for order in orders}
    refunds_by_payment: dict[str, list[Refund]] = {}
    for refund in refunds:
        if is_valid_refund_status(refund.refund_status):
            refunds_by_payment.setdefault(refund.payment_id, []).append(refund)

    attachments: dict[str, Settlement] = {}
    unresolved_orphans: list[Settlement] = []
    for settlement in orphan_candidates:
        candidate = _find_secondary_candidate(
            settlement,
            payments_by_id,
            direct_settlements,
            set(attachments),
        )
        if candidate is None:
            unresolved_orphans.append(settlement)
        else:
            attachments[candidate] = settlement

    payment_matches: list[PaymentMatch] = []
    for payment_id, occurrences in payments_by_id.items():
        primary = occurrences[0]
        group_settlements = list(direct_settlements[payment_id])
        match_method = "payment_id"
        confidence = EXACT_MATCH_CONFIDENCE
        attached = attachments.get(payment_id)
        if attached is not None:
            group_settlements.append(attached)
            match_method = "secondary_signals"
            confidence = SECONDARY_MATCH_CONFIDENCE
        payment_matches.append(
            PaymentMatch(
                payment=primary,
                duplicate_payment_rows=len(occurrences),
                order=orders_by_id.get(primary.order_id),
                settlements=group_settlements,
                valid_refunds=refunds_by_payment.get(payment_id, []),
                match_method=match_method,
                confidence=confidence,
            )
        )

    attached_ids = {id(settlement) for settlement in attachments.values()}
    remaining_orphans = [
        settlement
        for settlement in unresolved_orphans
        if id(settlement) not in attached_ids
    ]
    return MatchOutput(payment_matches=payment_matches, orphan_settlements=remaining_orphans)


def _find_secondary_candidate(
    settlement: Settlement,
    payments_by_id: dict[str, list[Payment]],
    direct_settlements: dict[str, list[Settlement]],
    already_attached: set[str],
) -> str | None:
    candidates = []
    for payment_id, occurrences in payments_by_id.items():
        if direct_settlements[payment_id] or payment_id in already_attached:
            continue
        if _is_secondary_match(settlement, occurrences[0]):
            candidates.append(payment_id)
    if len(candidates) == 1:
        return candidates[0]
    return None


def _is_secondary_match(settlement: Settlement, payment: Payment) -> bool:
    if settlement.currency != payment.currency:
        return False
    if abs(settlement.gross_amount - payment.amount) > SECONDARY_AMOUNT_WINDOW:
        return False
    day_gap = abs((settlement.settlement_date - payment.payment_date).days)
    return day_gap <= SECONDARY_DATE_WINDOW_DAYS
