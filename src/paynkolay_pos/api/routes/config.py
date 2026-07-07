"""Runtime metadata routes for the browser UI."""

from __future__ import annotations

from fastapi import APIRouter

from paynkolay_pos.api.schemas import ConfigResponse
from paynkolay_pos.config import CardBrand, load_runtime_settings
from paynkolay_pos.models import Currency, PaymentChannel

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", response_model=ConfigResponse)
async def get_config() -> ConfigResponse:
    """Return safe runtime configuration metadata for the browser."""

    supported_currencies = [currency.value for currency in Currency]
    supported_card_brands = [brand.value for brand in CardBrand]
    payment_channels = [channel.value for channel in PaymentChannel]

    try:
        settings = load_runtime_settings()
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return ConfigResponse(
            runtime_configured=False,
            supported_currencies=supported_currencies,
            supported_card_brands=supported_card_brands,
            payment_channels=payment_channels,
            message=str(exc),
        )

    current = settings.current
    return ConfigResponse(
        runtime_configured=True,
        active_environment=current.name.value,
        supported_currencies=supported_currencies,
        supported_card_brands=supported_card_brands,
        payment_channels=payment_channels,
        card_aliases=[card.alias for card in current.cards],
    )

