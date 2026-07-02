"""Typed payment scenario metadata for data-driven tests."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic.functional_validators import field_validator, model_validator

from paynkolay_pos.models import Currency, PaymentChannel, PaymentStatus


class StrictScenarioModel(BaseModel):
    """Base model that rejects unexpected scenario metadata."""

    model_config = {
        "extra": "forbid",
        "str_strip_whitespace": True,
        "use_enum_values": False,
    }


class PaymentScenario(StrictScenarioModel):
    """One reusable payment case for parameterized API and 3DS tests."""

    scenario_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    title: str = Field(min_length=1, max_length=160)
    card_alias: str = Field(min_length=1)
    amount: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2)
    currency: Currency = Currency.TRY
    requires_3ds: bool
    expected_initialize_status: PaymentStatus
    expected_final_status: PaymentStatus
    installment_count: int = Field(default=1, ge=1, le=12)
    payment_channel: PaymentChannel = PaymentChannel.E_COMMERCE
    moto: bool = False
    tags: tuple[str, ...] = ()

    @field_validator("amount")
    @classmethod
    def normalize_amount(cls, amount: Decimal) -> Decimal:
        """Keep scenario amounts comparable with payment request models."""

        return amount.quantize(Decimal("0.01"))

    @field_validator("tags")
    @classmethod
    def require_unique_tags(cls, tags: tuple[str, ...]) -> tuple[str, ...]:
        """Reject duplicate tags because pytest ids and filters should be stable."""

        if len(tags) != len(set(tags)):
            raise ValueError("scenario tags must be unique")
        return tags

    @model_validator(mode="after")
    def validate_channel_metadata(self) -> PaymentScenario:
        """Keep scenario metadata consistent with request model rules."""

        if self.moto and self.payment_channel is not PaymentChannel.MOTO:
            raise ValueError("moto scenarios must use payment_channel=moto")
        if not self.moto and self.payment_channel is PaymentChannel.MOTO:
            raise ValueError("payment_channel=moto requires moto=true")
        if self.moto and self.requires_3ds:
            raise ValueError("moto scenarios must not require 3DS")
        return self

    @property
    def canonical_amount(self) -> str:
        """Return the exact amount string used by payment request models."""

        return f"{self.amount:.2f}"

    def payment_request_payload(
        self,
        *,
        merchant_id: str,
        terminal_id: str,
        callback_url: str,
        card: Mapping[str, object],
        order_id: str,
        correlation_id: str,
    ) -> dict[str, object]:
        """Build a payment initialization payload from scenario metadata."""

        return {
            "merchant_id": merchant_id,
            "terminal_id": terminal_id,
            "order_id": order_id,
            "amount": self.canonical_amount,
            "currency": self.currency,
            "callback_url": callback_url,
            "card": dict(card),
            "requires_3ds": self.requires_3ds,
            "installment_count": self.installment_count,
            "payment_channel": self.payment_channel,
            "moto": self.moto,
            "correlation_id": correlation_id,
        }


class PaymentScenarioCatalog(StrictScenarioModel):
    """Validated collection of payment scenarios for parameterized tests."""

    scenarios: tuple[PaymentScenario, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_scenario_ids(self) -> PaymentScenarioCatalog:
        """Prevent ambiguous pytest parameter IDs and callback correlation."""

        scenario_ids = [scenario.scenario_id for scenario in self.scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("scenario_id values must be unique")
        return self

    def ids(self) -> tuple[str, ...]:
        """Return stable pytest parameter IDs."""

        return tuple(scenario.scenario_id for scenario in self.scenarios)

    def get(self, scenario_id: str) -> PaymentScenario:
        """Return one scenario by ID."""

        for scenario in self.scenarios:
            if scenario.scenario_id == scenario_id:
                return scenario
        raise KeyError(f"unknown payment scenario: {scenario_id}")

    def tagged(self, tag: str) -> tuple[PaymentScenario, ...]:
        """Return scenarios carrying a specific metadata tag."""

        return tuple(scenario for scenario in self.scenarios if tag in scenario.tags)


def load_payment_scenario_catalog(path: str | Path) -> PaymentScenarioCatalog:
    """Load and validate a payment scenario catalogue from a JSON file."""

    catalog_path = Path(path).expanduser()
    if not catalog_path.is_file():
        raise FileNotFoundError(f"payment scenario catalog does not exist: {catalog_path}")
    return PaymentScenarioCatalog.model_validate_json(catalog_path.read_text(encoding="utf-8"))
