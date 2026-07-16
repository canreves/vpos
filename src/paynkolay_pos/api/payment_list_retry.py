"""Retry helpers for Paynkolay PaymentList status verification."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from paynkolay_pos.api.payment_initializer import (
    PaymentProviderStatusVerificationError,
    SupportsPaymentInitializer,
)
from paynkolay_pos.models import Currency, PaymentStatus, TransactionStatusResponse

DEFAULT_PAYMENT_LIST_RETRY_DELAYS: tuple[float, ...] = (2.0, 5.0, 10.0)
async_sleep = asyncio.sleep


async def verify_transaction_status_with_retry(
    initializer: SupportsPaymentInitializer,
    order_id: str,
    *,
    currency: Currency,
    retry_delays: Sequence[float] = DEFAULT_PAYMENT_LIST_RETRY_DELAYS,
    accepted_statuses: set[PaymentStatus] | None = None,
) -> TransactionStatusResponse:
    """Verify transaction status, retrying transient lookup failures or non-final states."""

    last_error: PaymentProviderStatusVerificationError | None = None
    last_response: TransactionStatusResponse | None = None
    for attempt_index in range(len(retry_delays) + 1):
        try:
            response = await initializer.verify_transaction_status(order_id, currency=currency)
        except PaymentProviderStatusVerificationError as exc:
            last_error = exc
            if attempt_index == len(retry_delays):
                raise
            await async_sleep(retry_delays[attempt_index])
            continue

        if accepted_statuses is None or response.status in accepted_statuses:
            return response

        last_response = response
        if attempt_index == len(retry_delays):
            return response
        await async_sleep(retry_delays[attempt_index])

    if last_response is not None:
        return last_response
    raise RuntimeError("unreachable PaymentList retry state") from last_error
