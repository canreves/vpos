"""Pydantic schemas used by the FastAPI web layer."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator

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
    """Phase-1 payment response returned before provider execution is wired."""

    order_id: str
    status: Literal["created"]
    amount: str
    currency: Currency
    requires_3ds: bool
    message: str
    links: dict[str, str]


class PaymentLookupResponse(BaseModel):
    """Placeholder lookup response until session storage is introduced."""

    order_id: str
    status: Literal["not_tracked"]
    message: str


class ReportStatusResponse(BaseModel):
    """Local Allure report status exposed to the browser."""

    available: bool
    report_path: str
    entrypoint: str | None = None
    message: str

