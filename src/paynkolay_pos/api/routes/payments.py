"""Payment form routes for the browser UI."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status

from paynkolay_pos.api.dependencies import (
    get_external_payment_logger,
    get_payment_initializer,
    get_payment_session_store,
    get_three_ds_form_store,
)
from paynkolay_pos.api.payment_initializer import (
    PaymentProviderInitializationError,
    SupportsPaymentInitializer,
)
from paynkolay_pos.api.schemas import (
    PaymentFormRequest,
    PaymentFormResponse,
    PaymentLookupResponse,
)
from paynkolay_pos.api.session_models import PaymentSession, PaymentSessionStatus
from paynkolay_pos.api.session_store import (
    PaymentSessionAlreadyExistsError,
    PaymentSessionNotFoundError,
    PaymentSessionStore,
)
from paynkolay_pos.api.three_ds_store import ThreeDSFormStore
from paynkolay_pos.models import PaynkolayPaymentResult, PaynkolayThreeDSInitializeResult
from paynkolay_pos.reporting import (
    PaymentLogEvent,
    PaymentLogEventType,
    SupportsExternalPaymentLogger,
)

router = APIRouter(prefix="/api/payments", tags=["payments"])
PaymentSessionStoreDependency = Annotated[
    PaymentSessionStore,
    Depends(get_payment_session_store),
]
PaymentInitializerDependency = Annotated[
    SupportsPaymentInitializer,
    Depends(get_payment_initializer),
]
ThreeDSFormStoreDependency = Annotated[
    ThreeDSFormStore,
    Depends(get_three_ds_form_store),
]
ExternalLoggerDependency = Annotated[
    SupportsExternalPaymentLogger,
    Depends(get_external_payment_logger),
]


@router.post("", response_model=PaymentFormResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_payment(
    request: PaymentFormRequest,
    http_request: Request,
    session_store: PaymentSessionStoreDependency,
    three_ds_form_store: ThreeDSFormStoreDependency,
    initializer: PaymentInitializerDependency,
    external_logger: ExternalLoggerDependency,
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

    try:
        outcome = await initializer.initialize(
            request,
            order_id=order_id,
            card_holder_ip=_client_host(http_request),
        )
    except PaymentProviderInitializationError as exc:
        session = await session_store.update_status(
            order_id,
            PaymentSessionStatus.FAILED,
            failure_reason="provider payment initialization failed",
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=session.failure_reason,
        ) from exc

    provider_result = outcome.provider_result
    if isinstance(provider_result, PaynkolayThreeDSInitializeResult):
        await three_ds_form_store.put(
            order_id,
            provider_result.bank_request_message,
        )
        session = await session_store.update_status(
            order_id,
            PaymentSessionStatus.PENDING_3DS,
        )
        await _log_payment_event(
            external_logger,
            PaymentLogEventType.PAYMENT_INITIALIZED,
            session,
            metadata={"provider_result": "three_ds"},
        )
        await _log_payment_event(
            external_logger,
            PaymentLogEventType.THREE_DS_REQUIRED,
            session,
            metadata={"render_url": f"/payments/{order_id}/three-ds"},
        )
        three_ds = {"render_url": f"/payments/{order_id}/three-ds"}
        return PaymentFormResponse.from_session(
            session,
            message="Payment initialized; 3D Secure authentication is required.",
            three_ds=three_ds,
        )

    if isinstance(provider_result, PaynkolayPaymentResult):
        session_status = (
            PaymentSessionStatus.COMPLETED
            if provider_result.successful
            else PaymentSessionStatus.FAILED
        )
        session = await session_store.update_status(
            order_id,
            session_status,
            provider_transaction_id=provider_result.reference_code,
            failure_reason=(
                provider_result.response_data
                if session_status is PaymentSessionStatus.FAILED
                else None
            ),
        )
        await _log_payment_event(
            external_logger,
            PaymentLogEventType.PAYMENT_INITIALIZED,
            session,
            metadata={"provider_result": "final"},
        )
        return PaymentFormResponse.from_session(
            session,
            message="Payment provider returned a final payment result.",
        )

    raise TypeError(f"unsupported provider result type: {type(provider_result).__name__}")


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


def _client_host(request: Request) -> str:
    if request.client is None or not request.client.host.strip():
        return "127.0.0.1"
    return request.client.host


async def _log_payment_event(
    external_logger: SupportsExternalPaymentLogger,
    event_type: PaymentLogEventType,
    session: PaymentSession,
    *,
    metadata: dict[str, object] | None = None,
) -> None:
    try:
        event = PaymentLogEvent.from_session(
            event=event_type,
            session=session,
            metadata=metadata,
        )
        await external_logger.log(event)
    except Exception:
        return
