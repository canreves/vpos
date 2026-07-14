"""Paynkolay success/fail return URL routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
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

router = APIRouter(prefix="/payments/result", tags=["results"])
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


@router.api_route("/success", methods=["GET", "POST"], response_class=HTMLResponse)
async def payment_success_return(
    request: Request,
    session_store: PaymentSessionStoreDependency,
    merchant_secret_key: MerchantSecretDependency,
    external_logger: ExternalLoggerDependency,
) -> HTMLResponse:
    """Handle Paynkolay success URL returns."""

    return await _handle_payment_result_return(
        request,
        session_store=session_store,
        merchant_secret_key=merchant_secret_key,
        external_logger=external_logger,
    )


@router.api_route("/fail", methods=["GET", "POST"], response_class=HTMLResponse)
async def payment_fail_return(
    request: Request,
    session_store: PaymentSessionStoreDependency,
    merchant_secret_key: MerchantSecretDependency,
    external_logger: ExternalLoggerDependency,
) -> HTMLResponse:
    """Handle Paynkolay fail URL returns."""

    return await _handle_payment_result_return(
        request,
        session_store=session_store,
        merchant_secret_key=merchant_secret_key,
        external_logger=external_logger,
    )


async def _handle_payment_result_return(
    request: Request,
    *,
    session_store: PaymentSessionStore,
    merchant_secret_key: SecretStr,
    external_logger: SupportsExternalPaymentLogger,
) -> HTMLResponse:
    payload = await _request_payload(request)
    try:
        verified = verify_provider_payment_result(
            payload,
            merchant_secret_key=merchant_secret_key,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="provider result payload is invalid",
        ) from exc
    except PaymentResultHashVerificationError as exc:
        order_id = str(payload.get("CLIENT_REFERENCE_CODE", "")).strip()
        if order_id:
            await _mark_hash_failure_if_tracked(session_store, order_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    session = await _update_session_from_verified_result(
        session_store,
        verified,
    )
    await _log_result_event(external_logger, session, verified)
    return _result_html_response(session, verified)


async def _request_payload(request: Request) -> dict[str, object]:
    if request.method == "POST":
        form = await request.form()
        return dict(form)
    return dict(request.query_params)


async def _mark_hash_failure_if_tracked(
    session_store: PaymentSessionStore,
    order_id: str,
) -> None:
    try:
        await session_store.update_status(
            order_id,
            PaymentSessionStatus.FAILED,
            failure_reason="provider result hash verification failed",
        )
    except PaymentSessionNotFoundError:
        return


async def _update_session_from_verified_result(
    session_store: PaymentSessionStore,
    verified: VerifiedPaymentResult,
) -> PaymentSession:
    try:
        await session_store.get(verified.order_id)
    except PaymentSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    returned_status = (
        PaymentSessionStatus.SUCCESS_RETURNED
        if verified.result.successful
        else PaymentSessionStatus.FAIL_RETURNED
    )
    await session_store.update_status(
        verified.order_id,
        returned_status,
        provider_transaction_id=verified.provider_transaction_id,
        failure_reason=verified.failure_reason,
    )
    final_status = (
        PaymentSessionStatus.COMPLETED
        if verified.result.successful
        else PaymentSessionStatus.FAILED
    )
    return await session_store.update_status(
        verified.order_id,
        final_status,
        provider_transaction_id=verified.provider_transaction_id,
        failure_reason=verified.failure_reason,
    )


def _result_html_response(
    session: PaymentSession,
    verified: VerifiedPaymentResult,
) -> HTMLResponse:
    outcome = "Payment approved" if verified.result.successful else "Payment failed"
    status_class = "success" if verified.result.successful else "error"
    failure_row = ""
    if session.failure_reason:
        failure_row = (
            "<div>"
            "<dt>Reason</dt>"
            f"<dd>{_escape(session.failure_reason)}</dd>"
            "</div>"
        )
    amount = f"{session.canonical_amount} {session.currency.value}"
    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{_escape(outcome)}</title>
    <link rel="stylesheet" href="/static/css/app.css">
  </head>
  <body>
    <div class="shell">
      <header class="topbar">
        <div>
          <h1>Payment Result</h1>
          <p>Paynkolay POS</p>
        </div>
        <nav aria-label="Primary">
          <a class="nav-link" href="/">Payment</a>
          <a class="nav-link" href="/parallel">Parallel</a>
          <a class="nav-link" href="/settings">Settings</a>
          <a class="nav-link" href="/reports">Reports</a>
        </nav>
      </header>
      <main class="workspace single">
        <section class="panel">
          <div class="panel-heading">
            <h2>{_escape(outcome)}</h2>
            <span class="status-pill {status_class}">{_escape(session.status.value)}</span>
          </div>
          <dl class="result-list">
            <div><dt>Order ID</dt><dd>{_escape(session.order_id)}</dd></div>
            <div><dt>Reference</dt><dd>{_escape(verified.provider_transaction_id)}</dd></div>
            <div><dt>Amount</dt><dd>{_escape(amount)}</dd></div>
            <div><dt>Card</dt><dd>{_escape(session.masked_pan)}</dd></div>
            {failure_row}
          </dl>
        </section>
      </main>
    </div>
  </body>
</html>"""
    return HTMLResponse(
        content=html,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def _log_result_event(
    external_logger: SupportsExternalPaymentLogger,
    session: PaymentSession,
    verified: VerifiedPaymentResult,
) -> None:
    event_type = (
        PaymentLogEventType.PAYMENT_SUCCESS_RETURNED
        if verified.result.successful
        else PaymentLogEventType.PAYMENT_FAIL_RETURNED
    )
    try:
        event = PaymentLogEvent.from_session(
            event=event_type,
            session=session,
            metadata={"response_code": verified.result.response_code},
        )
        await external_logger.log(event)
    except Exception:
        return


def _escape(value: object) -> str:
    text = str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
