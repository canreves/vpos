"""Payment session state models for the web UI."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from paynkolay_pos.models import Currency, PaymentStatus


class ProviderRequestSummary(BaseModel):
    """Sanitized provider request fields safe to expose in UI diagnostics."""

    client_ref_code: str = Field(min_length=1, max_length=64)
    amount: str = Field(min_length=1, max_length=32)
    currency: Currency
    use_3d: bool
    installment_no: int = Field(ge=1, le=12)
    card_brand: str = Field(min_length=1, max_length=32)
    masked_pan: str = Field(min_length=8, max_length=24)
    expiry_month: int = Field(ge=1, le=12)
    expiry_year: int = Field(ge=2026, le=2100)
    transaction_type: str = Field(min_length=1, max_length=32)
    payment_channel: str = Field(min_length=1, max_length=32)
    success_url: str = Field(min_length=1, max_length=500)
    fail_url: str = Field(min_length=1, max_length=500)


class ThreeDSAutomationSummary(BaseModel):
    """Sanitized 3DS automation evidence safe to expose in UI/API responses."""

    status: str = Field(min_length=1, max_length=40)
    submitted: bool = False
    classification: str | None = Field(default=None, min_length=1, max_length=80)
    reason: str | None = Field(default=None, min_length=1, max_length=500)
    otp_source_type: str | None = Field(default=None, min_length=1, max_length=80)
    otp_present: bool = False
    should_auto_submit: bool = False
    final_url: str | None = Field(default=None, min_length=1, max_length=500)


class PaymentSessionStatus(StrEnum):
    """States tracked by the browser payment workflow."""

    CREATED = "created"
    SENT_TO_PROVIDER = "sent_to_provider"
    PENDING_3DS = "pending_3ds"
    THREE_DS_RENDERED = "three_ds_rendered"
    SUCCESS_RETURNED = "success_returned"
    FAIL_RETURNED = "fail_returned"
    STATUS_VERIFIED = "status_verified"
    CALLBACK_VERIFIED = "callback_verified"
    COMPLETED = "completed"
    FAILED = "failed"


class PaymentSession(BaseModel):
    """Sanitized payment session record kept for the browser workflow."""

    order_id: str = Field(min_length=1, max_length=64)
    status: PaymentSessionStatus
    amount: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2)
    currency: Currency
    masked_pan: str = Field(min_length=8, max_length=24)
    card_holder: str = Field(min_length=1, max_length=64)
    requires_3ds: bool
    installment_count: int = Field(ge=1, le=12)
    provider_request: ProviderRequestSummary | None = None
    provider_transaction_id: str | None = Field(default=None, min_length=1)
    provider_response_code: str | None = Field(default=None, min_length=1)
    provider_response_data: str | None = Field(default=None, min_length=1)
    failure_reason: str | None = Field(default=None, min_length=1)
    payment_list_status: PaymentStatus | None = None
    payment_list_provider_transaction_id: str | None = Field(default=None, min_length=1)
    payment_list_authorization_code: str | None = Field(default=None, min_length=1)
    payment_list_failure_code: str | None = Field(default=None, min_length=1)
    payment_list_updated_at: datetime | None = None
    payment_list_error: str | None = Field(default=None, min_length=1)
    three_ds_automation: ThreeDSAutomationSummary | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("amount")
    @classmethod
    def normalize_amount(cls, amount: Decimal) -> Decimal:
        """Keep session amounts in provider-friendly two-decimal format."""

        return amount.quantize(Decimal("0.01"))

    @field_validator("created_at", "updated_at", "payment_list_updated_at")
    @classmethod
    def require_timezone(cls, timestamp: datetime | None) -> datetime | None:
        """Normalize stored timestamps to UTC."""

        if timestamp is None:
            return None
        if timestamp.tzinfo is None:
            raise ValueError("session timestamps must include timezone information")
        return timestamp.astimezone(UTC)

    @property
    def canonical_amount(self) -> str:
        """Return the exact amount string shown by the browser API."""

        return f"{self.amount:.2f}"


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def mask_pan(pan: str) -> str:
    """Mask a card PAN for UI state and logs."""

    if not pan.isdigit():
        raise ValueError("PAN must contain digits only")
    if len(pan) < 12 or len(pan) > 19:
        raise ValueError("PAN must be between 12 and 19 digits")
    return f"{pan[:6]}{'*' * (len(pan) - 10)}{pan[-4:]}"
