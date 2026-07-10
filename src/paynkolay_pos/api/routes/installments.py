"""Installment option routes for the browser payment form."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter

from paynkolay_pos.api.schemas import (
    InstallmentOption,
    InstallmentOptionsRequest,
    InstallmentOptionsResponse,
)
from paynkolay_pos.models import Currency

router = APIRouter(prefix="/api/installments", tags=["installments"])


@router.post("/options", response_model=InstallmentOptionsResponse)
async def installment_options(request: InstallmentOptionsRequest) -> InstallmentOptionsResponse:
    """Return local stub installment options until the provider service is available."""

    counts = _stub_installment_counts(request)
    return InstallmentOptionsResponse(
        default_installment=1,
        source="local_stub",
        options=[
            InstallmentOption(
                installment_count=count,
                label=_installment_label(count),
                total_amount=request.canonical_amount,
                monthly_amount=_monthly_amount(request.amount, count),
            )
            for count in counts
        ],
    )


def _stub_installment_counts(request: InstallmentOptionsRequest) -> tuple[int, ...]:
    if request.currency is not Currency.TRY:
        return (1,)
    if request.amount < Decimal("100.00"):
        return (1,)
    return (1, 2, 3, 6, 9, 12)


def _installment_label(count: int) -> str:
    if count == 1:
        return "Tek cekim"
    return f"{count} taksit"


def _monthly_amount(amount: Decimal, count: int) -> str:
    return f"{(amount / Decimal(count)).quantize(Decimal('0.01')):.2f}"
