"""Payment form routes for the browser UI."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, status

from paynkolay_pos.api.schemas import (
    PaymentFormRequest,
    PaymentFormResponse,
    PaymentLookupResponse,
)

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.post("", response_model=PaymentFormResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_payment(request: PaymentFormRequest) -> PaymentFormResponse:
    """Accept and validate a browser payment form payload.

    Provider execution and payment session storage are intentionally left for the next
    implementation phases; this route establishes the public API contract.
    """

    order_id = request.order_id or f"web-{uuid4().hex[:12]}"
    return PaymentFormResponse(
        order_id=order_id,
        status="created",
        amount=request.canonical_amount,
        currency=request.currency,
        requires_3ds=request.requires_3ds,
        message="Payment form accepted; provider execution will be attached in phase 3.",
        links={
            "status": f"/api/payments/{order_id}",
            "result": f"/result?order_id={order_id}",
        },
    )


@router.get("/{order_id}", response_model=PaymentLookupResponse)
async def get_payment(order_id: str) -> PaymentLookupResponse:
    """Return a placeholder lookup response until phase-2 session storage exists."""

    return PaymentLookupResponse(
        order_id=order_id,
        status="not_tracked",
        message="Payment session storage will be introduced in phase 2.",
    )

