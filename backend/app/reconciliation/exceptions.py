from __future__ import annotations

from enum import Enum


class ExceptionType(str, Enum):
    NONE = "NONE"
    MISSING_SETTLEMENT = "MISSING_SETTLEMENT"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    DUPLICATE_TRANSACTION = "DUPLICATE_TRANSACTION"
    FEE_MISMATCH = "FEE_MISMATCH"
    TAX_MISMATCH = "TAX_MISMATCH"
    REFUND_NOT_SETTLED = "REFUND_NOT_SETTLED"
    DATE_MISMATCH = "DATE_MISMATCH"
    UNKNOWN_TRANSACTION = "UNKNOWN_TRANSACTION"


CLASSIFICATION_PRIORITY = [
    ExceptionType.DUPLICATE_TRANSACTION,
    ExceptionType.MISSING_SETTLEMENT,
    ExceptionType.UNKNOWN_TRANSACTION,
    ExceptionType.REFUND_NOT_SETTLED,
    ExceptionType.AMOUNT_MISMATCH,
    ExceptionType.FEE_MISMATCH,
    ExceptionType.TAX_MISMATCH,
    ExceptionType.DATE_MISMATCH,
]

RECOMMENDATIONS: dict[ExceptionType, str] = {
    ExceptionType.MISSING_SETTLEMENT: "Confirm payout with the gateway and re-run reconciliation.",
    ExceptionType.AMOUNT_MISMATCH: "Compare payment and settlement gross amounts against gateway reports.",
    ExceptionType.DUPLICATE_TRANSACTION: "Review duplicated records and remove the erroneous ingest.",
    ExceptionType.FEE_MISMATCH: "Verify the gateway processing fee schedule for this transaction.",
    ExceptionType.TAX_MISMATCH: "Verify tax applied on the processing fee.",
    ExceptionType.REFUND_NOT_SETTLED: "Ensure processed refunds are deducted from the settlement.",
    ExceptionType.DATE_MISMATCH: "Check settlement timing against the expected payout cycle.",
    ExceptionType.UNKNOWN_TRANSACTION: "Locate or create the payment record referenced by this settlement.",
}


def classify(findings: set[ExceptionType]) -> ExceptionType:
    for candidate in CLASSIFICATION_PRIORITY:
        if candidate in findings:
            return candidate
    return ExceptionType.NONE
