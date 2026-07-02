"""Callback and webhook payload models for Sanal POS notifications."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from pydantic import Field, field_validator, model_validator

from paynkolay_pos.models.payments import Currency, PaymentStatus, StrictPaymentModel


class CallbackPayload(StrictPaymentModel):
    """Validated provider callback body sent to the merchant backend."""

    order_id: str = Field(min_length=1)
    provider_transaction_id: str = Field(min_length=1)
    status: PaymentStatus
    amount: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2)
    currency: Currency
    received_at: datetime
    signature: str = Field(min_length=64, max_length=128)
    authorization_code: str | None = Field(default=None, min_length=1)
    failure_code: str | None = Field(default=None, min_length=1)

    @field_validator("amount")
    @classmethod
    def normalize_amount(cls, amount: Decimal) -> Decimal:
        """Keep callback amounts comparable with request and status amounts."""

        return amount.quantize(Decimal("0.01"))

    @field_validator("received_at")
    @classmethod
    def require_timezone(cls, received_at: datetime) -> datetime:
        """Reject naive callback timestamps because ordering depends on timezones."""

        if received_at.tzinfo is None:
            raise ValueError("received_at must include timezone information")
        return received_at.astimezone(UTC)

    @model_validator(mode="after")
    def validate_status_evidence(self) -> CallbackPayload:
        """Require status-specific callback evidence for final outcomes."""

        if (
            self.status in {PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED}
            and self.authorization_code is None
        ):
            raise ValueError("approved callbacks must include authorization_code")
        if self.status is PaymentStatus.FAILED and self.failure_code is None:
            raise ValueError("failed callbacks must include failure_code")
        return self

    @property
    def canonical_amount(self) -> str:
        """Return the exact callback amount string used in signature checks."""

        return f"{self.amount:.2f}"

    def signature_payload(self) -> dict[str, object]:
        """Return non-secret callback fields that participate in signature verification."""

        return {
            "order_id": self.order_id,
            "provider_transaction_id": self.provider_transaction_id,
            "status": self.status,
            "amount": self.canonical_amount,
            "currency": self.currency,
            "received_at": self.received_at.isoformat().replace("+00:00", "Z"),
        }
