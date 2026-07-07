"""Provider payment initialization adapter for the web API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from paynkolay_pos.api.schemas import PaymentFormRequest
from paynkolay_pos.clients import PaynkolayClient
from paynkolay_pos.config import PaymentEnvironment
from paynkolay_pos.models import (
    PaymentCardInput,
    PaymentInitializeRequest,
    PaynkolayPaymentResult,
    PaynkolayThreeDSInitializeResult,
    parse_paynkolay_payment_result,
)


class PaymentProviderInitializationError(RuntimeError):
    """Raised when provider payment initialization cannot be completed."""


@dataclass(frozen=True)
class PaymentInitializationOutcome:
    """Typed result returned after a provider initialization attempt."""

    payment_request: PaymentInitializeRequest
    provider_result: PaynkolayThreeDSInitializeResult | PaynkolayPaymentResult
    success_url: str
    fail_url: str


class SupportsPaymentInitializer(Protocol):
    """Behavior required by payment routes to initialize provider payments."""

    async def initialize(
        self,
        request: PaymentFormRequest,
        *,
        order_id: str,
        card_holder_ip: str,
    ) -> PaymentInitializationOutcome:
        """Initialize a payment through the configured provider."""


class PaynkolayPaymentInitializer:
    """Build Paynkolay form requests and parse provider initialization results."""

    def __init__(
        self,
        *,
        environment: PaymentEnvironment,
        client: PaynkolayClient,
    ) -> None:
        self._environment = environment
        self._client = client

    async def initialize(
        self,
        request: PaymentFormRequest,
        *,
        order_id: str,
        card_holder_ip: str,
    ) -> PaymentInitializationOutcome:
        """Initialize a Paynkolay form payment using the existing provider client."""

        payment_request = self._payment_request(request, order_id=order_id)
        success_url = _provider_url(
            self._environment.callback_base_url,
            "/payments/result/success",
        )
        fail_url = _provider_url(
            self._environment.callback_base_url,
            "/payments/result/fail",
        )
        try:
            provider_payload = await self._client.initialize_payment_form(
                payment_request,
                success_url=success_url,
                fail_url=fail_url,
                card_holder_ip=card_holder_ip,
            )
            provider_result = parse_paynkolay_payment_result(provider_payload)
        except (httpx.HTTPError, RuntimeError, TypeError, ValueError) as exc:
            raise PaymentProviderInitializationError(
                "provider payment initialization failed"
            ) from exc

        return PaymentInitializationOutcome(
            payment_request=payment_request,
            provider_result=provider_result,
            success_url=success_url,
            fail_url=fail_url,
        )

    def _payment_request(
        self,
        request: PaymentFormRequest,
        *,
        order_id: str,
    ) -> PaymentInitializeRequest:
        callback_url = _provider_url(
            self._environment.callback_base_url,
            "/callbacks/paynkolay",
        )
        return PaymentInitializeRequest(
            merchant_id=self._environment.merchant.merchant_id,
            terminal_id=self._environment.merchant.terminal_id,
            order_id=order_id,
            amount=request.amount,
            currency=request.currency,
            callback_url=callback_url,
            card=PaymentCardInput(
                brand=request.card_brand,
                pan=request.card_number,
                expiry_month=request.expiry_month,
                expiry_year=request.expiry_year,
                cvv=request.cvv,
                card_holder=request.card_holder,
            ),
            requires_3ds=request.requires_3ds,
            installment_count=request.installment_count,
            correlation_id=f"web-{order_id}",
        )


def _provider_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"

