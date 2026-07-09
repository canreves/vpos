"""Paynkolay callback routes for UAT payment result capture."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import SecretStr, ValidationError

from paynkolay_pos.api.dependencies import (
    get_external_payment_logger,
    get_merchant_secret_key,
    get_payment_session_store,
)
from paynkolay_pos.api.payment_results import (
    PaymentResultHashVerificationError,
    VerifiedPaymentResult,
    verify_provider_payment_result,
)
from paynkolay_pos.api.session_models import PaymentSession, PaymentSessionStatus
from paynkolay_pos.api.session_store import (
    PaymentSessionNotFoundError,
    PaymentSessionStore,
)
from paynkolay_pos.reporting import (
    PaymentLogEvent,
    PaymentLogEventType,
    SupportsExternalPaymentLogger,
)

router = APIRouter(prefix="/callbacks", tags=["callbacks"])
PaymentSessionStoreDependency = Annotated[
    PaymentSessionStore,
    Depends(get_payment_session_store),
]
MerchantSecretDependency = Annotated[
    SecretStr,
    Depends(get_merchant_secret_key),
]
ExternalLoggerDependency = Annotated[
    SupportsExternalPaymentLogger,
    Depends(get_external_payment_logger),
]


@router.api_route("/paynkolay", methods=["GET", "POST"], status_code=status.HTTP_202_ACCEPTED)
async def paynkolay_callback(
    request: Request,
    session_store: PaymentSessionStoreDependency,
    merchant_secret_key: MerchantSecretDependency,
    external_logger: ExternalLoggerDependency,
) -> dict[str, object]:
    """Accept and verify Paynkolay UAT callbacks.

    Paynkolay callback payloads use the same payment-result fields and ``hashDataV2``
    response hash contract as success/fail returns. The route updates in-memory web
    session state when the order is known, but still accepts verified callbacks for
    externally initiated UAT runs.
    """

    payload = await _request_payload(request)
    try:
        verified = verify_provider_payment_result(
            payload,
            merchant_secret_key=merchant_secret_key,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="callback payload is invalid",
        ) from exc
    except PaymentResultHashVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    session = await _update_tracked_session_if_present(session_store, verified)
    await _log_callback_event(external_logger, session)
    return {
        "accepted": True,
        "tracked": session is not None,
        "order_id": verified.order_id,
        "provider_transaction_id": verified.provider_transaction_id,
        "successful": verified.result.successful,
    }


async def _request_payload(request: Request) -> dict[str, object]:
    if request.method == "POST":
        form = await request.form()
        return dict(form)
    return dict(request.query_params)


async def _update_tracked_session_if_present(
    session_store: PaymentSessionStore,
    verified: VerifiedPaymentResult,
) -> PaymentSession | None:
    try:
        await session_store.get(verified.order_id)
    except PaymentSessionNotFoundError:
        return None

    callback_status = (
        PaymentSessionStatus.COMPLETED
        if verified.result.successful
        else PaymentSessionStatus.FAILED
    )
    return await session_store.update_status(
        verified.order_id,
        callback_status,
        provider_transaction_id=verified.provider_transaction_id,
        failure_reason=verified.failure_reason,
    )


async def _log_callback_event(
    external_logger: SupportsExternalPaymentLogger,
    session: PaymentSession | None,
) -> None:
    if session is None:
        return
    try:
        event = PaymentLogEvent.from_session(
            event=PaymentLogEventType.CALLBACK_RECEIVED,
            session=session,
            metadata={"source": "paynkolay_callback"},
        )
        await external_logger.log(event)
    except Exception:
        return
