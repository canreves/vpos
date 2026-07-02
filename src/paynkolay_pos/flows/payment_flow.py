"""High-level payment workflows built on top of provider clients."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Protocol

from paynkolay_pos.models import (
    PaymentInitializeRequest,
    PaymentInitializeResponse,
    PaymentStatus,
    TransactionStatusResponse,
)

FINAL_PAYMENT_STATUSES = frozenset(
    {
        PaymentStatus.AUTHORIZED,
        PaymentStatus.CAPTURED,
        PaymentStatus.FAILED,
        PaymentStatus.CANCELLED,
        PaymentStatus.REFUNDED,
    }
)


class SupportsPaymentInitialization(Protocol):
    """Client behavior required by payment flow orchestration."""

    async def initialize_payment(
        self,
        request: PaymentInitializeRequest,
    ) -> PaymentInitializeResponse:
        """Initialize a payment through the provider."""

    async def get_transaction_status(self, order_id: str) -> TransactionStatusResponse:
        """Fetch a transaction's latest provider status."""


class PaymentFlow:
    """Business-readable orchestration for payment scenarios."""

    def __init__(
        self,
        client: SupportsPaymentInitialization,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._client = client
        self._sleep = sleep
        self._clock = clock

    async def initialize(
        self,
        request: PaymentInitializeRequest,
    ) -> PaymentInitializeResponse:
        """Initialize a payment and return the provider's typed business state."""

        return await self._client.initialize_payment(request)

    async def wait_for_final_status(
        self,
        order_id: str,
        *,
        timeout_seconds: float = 60.0,
        poll_interval_seconds: float = 2.0,
    ) -> TransactionStatusResponse:
        """Poll provider status until the transaction reaches a final state."""

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than zero")

        deadline = self._clock() + timeout_seconds
        last_status: PaymentStatus | None = None

        while self._clock() <= deadline:
            status_response = await self._client.get_transaction_status(order_id)
            last_status = status_response.status
            if status_response.status in FINAL_PAYMENT_STATUSES:
                return status_response
            await self._sleep(poll_interval_seconds)

        raise TimeoutError(
            f"transaction {order_id!r} did not reach a final status within "
            f"{timeout_seconds:.2f}s; last status was {last_status!s}"
        )
