"""3D Secure browser rendering routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse

from paynkolay_pos.api.dependencies import (
    get_external_payment_logger,
    get_payment_session_store,
    get_three_ds_form_store,
)
from paynkolay_pos.api.session_models import PaymentSession, PaymentSessionStatus
from paynkolay_pos.api.session_store import (
    PaymentSessionNotFoundError,
    PaymentSessionStore,
)
from paynkolay_pos.api.three_ds_store import ThreeDSFormNotFoundError, ThreeDSFormStore
from paynkolay_pos.reporting import (
    PaymentLogEvent,
    PaymentLogEventType,
    SupportsExternalPaymentLogger,
)
from paynkolay_pos.three_ds import ThreeDSFormPayloadError, render_three_ds_form

router = APIRouter(tags=["three_ds"])
PaymentSessionStoreDependency = Annotated[
    PaymentSessionStore,
    Depends(get_payment_session_store),
]
ThreeDSFormStoreDependency = Annotated[
    ThreeDSFormStore,
    Depends(get_three_ds_form_store),
]
ExternalLoggerDependency = Annotated[
    SupportsExternalPaymentLogger,
    Depends(get_external_payment_logger),
]


@router.get("/payments/{order_id}/three-ds", response_class=HTMLResponse)
async def render_three_ds_challenge(
    order_id: str,
    session_store: PaymentSessionStoreDependency,
    form_store: ThreeDSFormStoreDependency,
    external_logger: ExternalLoggerDependency,
) -> HTMLResponse:
    """Render the provider 3DS form for a pending browser payment."""

    try:
        session = await session_store.get(order_id)
    except PaymentSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if session.status not in {
        PaymentSessionStatus.PENDING_3DS,
        PaymentSessionStatus.THREE_DS_RENDERED,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"payment session is not waiting for 3DS: status={session.status.value!r}",
        )

    try:
        raw_form = await form_store.get(order_id)
        document = render_three_ds_form(raw_form)
    except ThreeDSFormNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ThreeDSFormPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    session = await session_store.update_status(
        order_id,
        PaymentSessionStatus.THREE_DS_RENDERED,
    )
    await _log_payment_event(external_logger, session)
    return HTMLResponse(
        content=document.html,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def _log_payment_event(
    external_logger: SupportsExternalPaymentLogger,
    session: PaymentSession,
) -> None:
    try:
        event = PaymentLogEvent.from_session(
            event=PaymentLogEventType.THREE_DS_RENDERED,
            session=session,
        )
        await external_logger.log(event)
    except Exception:
        return
