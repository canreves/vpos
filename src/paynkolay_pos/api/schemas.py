"""Pydantic schemas used by the FastAPI web layer."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator

from paynkolay_pos.api.session_models import PaymentSession, PaymentSessionStatus
from paynkolay_pos.models import Currency


class HealthResponse(BaseModel):
    """Health check payload returned by the web app."""

    status: Literal["ok"]
    service: str
    version: str


class ConfigResponse(BaseModel):
    """Safe runtime metadata exposed to the browser."""

    runtime_configured: bool
    active_environment: str | None = None
    supported_currencies: list[str]
    supported_card_brands: list[str]
    payment_channels: list[str]
    card_aliases: list[str] = Field(default_factory=list)
    message: str | None = None


class PaymentFormRequest(BaseModel):
    """Payment form payload accepted from the browser."""

    order_id: str | None = Field(default=None, min_length=1, max_length=64)
    amount: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2)
    currency: Currency = Currency.TRY
    card_number: SecretStr = Field(min_length=12, max_length=19)
    card_holder: str = Field(min_length=1, max_length=64)
    expiry_month: int = Field(ge=1, le=12)
    expiry_year: int = Field(ge=2026, le=2100)
    cvv: SecretStr = Field(min_length=3, max_length=4)
    requires_3ds: bool = True
    installment_count: int = Field(default=1, ge=1, le=12)

    @field_validator("amount")
    @classmethod
    def normalize_amount(cls, amount: Decimal) -> Decimal:
        """Keep browser-submitted amounts in provider-friendly two-decimal format."""

        return amount.quantize(Decimal("0.01"))

    def model_post_init(self, __context: object) -> None:
        """Validate sensitive numeric fields after SecretStr parsing."""

        card_number = self.card_number.get_secret_value()
        if not card_number.isdigit():
            raise ValueError("card_number must contain digits only")

        cvv = self.cvv.get_secret_value()
        if not cvv.isdigit():
            raise ValueError("cvv must contain digits only")

    @property
    def canonical_amount(self) -> str:
        """Return the exact amount string used in UI responses."""

        return f"{self.amount:.2f}"


class PaymentFormResponse(BaseModel):
    """Payment creation response returned to the browser."""

    order_id: str
    status: PaymentSessionStatus
    amount: str
    currency: Currency
    masked_pan: str
    requires_3ds: bool
    message: str
    links: dict[str, str]

    @classmethod
    def from_session(cls, session: PaymentSession) -> PaymentFormResponse:
        """Build a browser response from sanitized session state."""

        return cls(
            order_id=session.order_id,
            status=session.status,
            amount=session.canonical_amount,
            currency=session.currency,
            masked_pan=session.masked_pan,
            requires_3ds=session.requires_3ds,
            message="Payment session created; provider execution will be attached in phase 3.",
            links={
                "status": f"/api/payments/{session.order_id}",
                "result": f"/result?order_id={session.order_id}",
            },
        )


class PaymentLookupResponse(BaseModel):
    """Sanitized payment session state returned by lookup routes."""

    order_id: str
    status: PaymentSessionStatus
    amount: str
    currency: Currency
    masked_pan: str
    card_holder: str
    requires_3ds: bool
    installment_count: int
    provider_transaction_id: str | None = None
    failure_reason: str | None = None
    created_at: str
    updated_at: str
    links: dict[str, str]

    @classmethod
    def from_session(cls, session: PaymentSession) -> PaymentLookupResponse:
        """Build a lookup response from sanitized session state."""

        return cls(
            order_id=session.order_id,
            status=session.status,
            amount=session.canonical_amount,
            currency=session.currency,
            masked_pan=session.masked_pan,
            card_holder=session.card_holder,
            requires_3ds=session.requires_3ds,
            installment_count=session.installment_count,
            provider_transaction_id=session.provider_transaction_id,
            failure_reason=session.failure_reason,
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            links={
                "result": f"/result?order_id={session.order_id}",
            },
        )


class ReportStatusResponse(BaseModel):
    """Local Allure report status exposed to the browser."""

    available: bool
    report_path: str
    entrypoint: str | None = None
    message: str
