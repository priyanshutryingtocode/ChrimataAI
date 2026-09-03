from __future__ import annotations

from app.adapters.base import FetchParams, RealDataAdapter
from app.core.config import settings
from app.models.transaction import SourceData


class RazorpayAdapter(RealDataAdapter):
    """
    Maps Razorpay API objects to the canonical 4-source schema:

      Razorpay Order    -> app.models.transaction.Order
      Razorpay Payment  -> app.models.transaction.Payment
      Razorpay Settlement (payout) -> app.models.transaction.Settlement
      Razorpay Refund   -> app.models.transaction.Refund

    All monetary fields remain Decimal; IDs are normalized via
    reconciliation.normalize helpers downstream. The adapter itself
    never performs financial comparisons — it only fetches and maps.
    """

    def validate_credentials(self) -> bool:
        return bool(settings.razorpay_key_id.strip() and settings.razorpay_key_secret.strip())

    def fetch(self, params: FetchParams | None = None) -> SourceData:  # noqa: ARG002
        if not self.validate_credentials():
            raise NotImplementedError(
                "Razorpay credentials not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in backend/.env. "
                "When configured, implement paginated calls to Razorpay Orders/Payments/Settlements/Refunds APIs "
                "and map each payload to the canonical dataclasses in app.models.transaction."
            )
        raise NotImplementedError(
            "Razorpay live fetch not yet implemented. Wire the Razorpay Python SDK here, "
            "paginate through the date range in FetchParams, and return a SourceData."
        )

    def fetch_orders(self, params: FetchParams | None = None) -> list:  # noqa: ARG002
        raise NotImplementedError("Implement Razorpay Orders fetch when credentials are available.")

    def fetch_payments(self, params: FetchParams | None = None) -> list:  # noqa: ARG002
        raise NotImplementedError("Implement Razorpay Payments fetch when credentials are available.")

    def fetch_settlements(self, params: FetchParams | None = None) -> list:  # noqa: ARG002
        raise NotImplementedError("Implement Razorpay Settlements fetch when credentials are available.")

    def fetch_refunds(self, params: FetchParams | None = None) -> list:  # noqa: ARG002
        raise NotImplementedError("Implement Razorpay Refunds fetch when credentials are available.")
