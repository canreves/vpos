"""High-level payment workflows built on top of provider clients."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Protocol

from pydantic import SecretStr

from paynkolay_pos.callbacks import CallbackMatcher, require_valid_callback_signature
from paynkolay_pos.models import (
    CallbackPayload,
    PaymentInitializeRequest,
    PaymentInitializeResponse,
    PaymentStatus,
    TransactionStatusResponse,
)
from paynkolay_pos.security import SignatureAlgorithm

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


class SupportsCallbackMatching(Protocol):
    """Callback store behavior required by payment flow orchestration."""

    async def wait_for(
        self,
        order_id: str,
        *,
        matcher: CallbackMatcher | None = None,
        timeout_seconds: float = 30.0,
        poll_interval_seconds: float = 0.5,
    ) -> CallbackPayload:
        """Wait for a callback matching an order ID and optional predicate."""


class PaymentFlowCallbackMismatchError(AssertionError):
    """Raised when a verified callback disagrees with payment evidence."""


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

    async def wait_for_verified_callback(
        self,
        request: PaymentInitializeRequest,
        final_status: TransactionStatusResponse,
        *,
        callback_store: SupportsCallbackMatching,
        secret_key: SecretStr | str,
        algorithm: SignatureAlgorithm = SignatureAlgorithm.HMAC_SHA256,
        timeout_seconds: float = 30.0,
        poll_interval_seconds: float = 0.5,
    ) -> CallbackPayload:
        """Wait for, verify, and cross-check the provider callback for a payment."""

        self._require_status_matches_request(request, final_status)
        callback = await callback_store.wait_for(
            request.order_id,
            matcher=lambda stored_callback: (
                stored_callback.provider_transaction_id == final_status.provider_transaction_id
                and stored_callback.status == final_status.status
            ),
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        require_valid_callback_signature(
            callback,
            secret_key=secret_key,
            algorithm=algorithm,
        )
        self._require_callback_matches_payment(request, final_status, callback)
        return callback

    def _require_status_matches_request(
        self,
        request: PaymentInitializeRequest,
        final_status: TransactionStatusResponse,
    ) -> None:
        """Ensure the final status belongs to the initialized payment request."""

        if final_status.order_id != request.order_id:
            raise PaymentFlowCallbackMismatchError(
                "transaction status order_id does not match payment request: "
                f"request={request.order_id!r}, status={final_status.order_id!r}"
            )
        if final_status.amount != request.amount:
            raise PaymentFlowCallbackMismatchError(
                "transaction status amount does not match payment request: "
                f"request={request.canonical_amount}, status={final_status.amount:.2f}"
            )
        if final_status.currency != request.currency:
            raise PaymentFlowCallbackMismatchError(
                "transaction status currency does not match payment request: "
                f"request={request.currency}, status={final_status.currency}"
            )

    def _require_callback_matches_payment(
        self,
        request: PaymentInitializeRequest,
        final_status: TransactionStatusResponse,
        callback: CallbackPayload,
    ) -> None:
        """Ensure verified callback evidence agrees with request and status query."""

        if callback.order_id != request.order_id:
            raise PaymentFlowCallbackMismatchError(
                "callback order_id does not match payment request: "
                f"request={request.order_id!r}, callback={callback.order_id!r}"
            )
        if callback.provider_transaction_id != final_status.provider_transaction_id:
            raise PaymentFlowCallbackMismatchError(
                "callback provider_transaction_id does not match transaction status: "
                f"status={final_status.provider_transaction_id!r}, "
                f"callback={callback.provider_transaction_id!r}"
            )
        if callback.status != final_status.status:
            raise PaymentFlowCallbackMismatchError(
                "callback status does not match transaction status: "
                f"status={final_status.status}, callback={callback.status}"
            )
        if callback.amount != request.amount or callback.amount != final_status.amount:
            raise PaymentFlowCallbackMismatchError(
                "callback amount does not match payment evidence: "
                f"request={request.canonical_amount}, status={final_status.amount:.2f}, "
                f"callback={callback.canonical_amount}"
            )
        if callback.currency != request.currency or callback.currency != final_status.currency:
            raise PaymentFlowCallbackMismatchError(
                "callback currency does not match payment evidence: "
                f"request={request.currency}, status={final_status.currency}, "
                f"callback={callback.currency}"
            )
