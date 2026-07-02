"""High-level payment workflows built on top of provider clients."""

from __future__ import annotations

from typing import Protocol

from paynkolay_pos.models import PaymentInitializeRequest, PaymentInitializeResponse


class SupportsPaymentInitialization(Protocol):
    """Client behavior required by the first payment flow step."""

    async def initialize_payment(
        self,
        request: PaymentInitializeRequest,
    ) -> PaymentInitializeResponse:
        """Initialize a payment through the provider."""


class PaymentFlow:
    """Business-readable orchestration for payment scenarios."""

    def __init__(self, client: SupportsPaymentInitialization) -> None:
        self._client = client

    async def initialize(
        self,
        request: PaymentInitializeRequest,
    ) -> PaymentInitializeResponse:
        """Initialize a payment and return the provider's typed business state."""

        return await self._client.initialize_payment(request)
