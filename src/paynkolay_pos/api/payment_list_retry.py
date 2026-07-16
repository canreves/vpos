"""Retry helpers for Paynkolay PaymentList status verification."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from paynkolay_pos.api.payment_initializer import (
    PaymentProviderStatusVerificationError,
    SupportsPaymentInitializer,
)
from paynkolay_pos.models import Currency, TransactionStatusResponse

DEFAULT_PAYMENT_LIST_RETRY_DELAYS: tuple[float, ...] = (2.0, 5.0, 10.0)
async_sleep = asyncio.sleep


async def verify_transaction_status_with_retry(
    initializer: SupportsPaymentInitializer,
    order_id: str,
    *,
    currency: Currency,
    retry_delays: Sequence[float] = DEFAULT_PAYMENT_LIST_RETRY_DELAYS,
) -> TransactionStatusResponse:
    """Verify transaction status, retrying transient PaymentList lookup failures."""

    last_error: PaymentProviderStatusVerificationError | None = None
    for attempt_index in range(len(retry_delays) + 1):
        try:
            return await initializer.verify_transaction_status(order_id, currency=currency)
        except PaymentProviderStatusVerificationError as exc:
            last_error = exc
            if attempt_index == len(retry_delays):
                raise
            await async_sleep(retry_delays[attempt_index])

    raise RuntimeError("unreachable PaymentList retry state") from last_error
