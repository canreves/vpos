"""Payment form routes for the browser UI."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from paynkolay_pos.api.dependencies import get_payment_session_store
from paynkolay_pos.api.schemas import (
    PaymentFormRequest,
    PaymentFormResponse,
    PaymentLookupResponse,
)
from paynkolay_pos.api.session_store import (
    PaymentSessionAlreadyExistsError,
    PaymentSessionNotFoundError,
    PaymentSessionStore,
)

router = APIRouter(prefix="/api/payments", tags=["payments"])
PaymentSessionStoreDependency = Annotated[
    PaymentSessionStore,
    Depends(get_payment_session_store),
]


@router.post("", response_model=PaymentFormResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_payment(
    request: PaymentFormRequest,
    session_store: PaymentSessionStoreDependency,
) -> PaymentFormResponse:
    """Accept and validate a browser payment form payload.

    Provider execution is intentionally left for the next implementation phases; this route
    creates sanitized session state for the browser workflow.
    """

    order_id = request.order_id or f"web-{uuid4().hex[:12]}"
    try:
        session = await session_store.create(
            order_id=order_id,
            amount=request.amount,
            currency=request.currency,
            pan=request.card_number.get_secret_value(),
            card_holder=request.card_holder,
            requires_3ds=request.requires_3ds,
            installment_count=request.installment_count,
        )
    except PaymentSessionAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return PaymentFormResponse.from_session(session)


@router.get("/{order_id}", response_model=PaymentLookupResponse)
async def get_payment(
    order_id: str,
    session_store: PaymentSessionStoreDependency,
) -> PaymentLookupResponse:
    """Return sanitized session state for an order ID."""

    try:
        session = await session_store.get(order_id)
    except PaymentSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return PaymentLookupResponse.from_session(session)
