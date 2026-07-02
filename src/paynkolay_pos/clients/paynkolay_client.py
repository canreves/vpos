"""Async HTTP client boundary for Paynkolay Sanal POS API calls."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from paynkolay_pos.config import PaymentEnvironment
from paynkolay_pos.models import PaymentInitializeRequest, PaymentInitializeResponse
from paynkolay_pos.security import canonicalize_fields, generate_hmac_signature

PAYMENT_INITIALIZE_SIGNATURE_FIELDS = (
    "merchant_id",
    "terminal_id",
    "order_id",
    "amount",
    "currency",
    "callback_url",
    "requires_3ds",
    "correlation_id",
)


class PaynkolayClient:
    """Small wrapper around HTTPX that centralizes provider HTTP behavior."""

    def __init__(
        self,
        environment: PaymentEnvironment,
        *,
        timeout: httpx.Timeout | float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._environment = environment
        self._client = httpx.AsyncClient(
            base_url=environment.base_url,
            timeout=timeout,
            transport=transport,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Merchant-Id": environment.merchant.merchant_id,
                "X-Terminal-Id": environment.merchant.terminal_id,
            },
        )

    @property
    def base_url(self) -> str:
        """Return the provider base URL selected by runtime configuration."""

        return str(self._client.base_url)

    async def post_json(
        self,
        path: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """POST JSON to a provider endpoint and return the decoded object body."""

        response = await self._client.post(path, json=payload)
        response.raise_for_status()
        decoded = response.json()
        if not isinstance(decoded, dict):
            raise TypeError("provider response must be a JSON object")
        return decoded

    async def initialize_payment(
        self,
        request: PaymentInitializeRequest,
    ) -> PaymentInitializeResponse:
        """Sign, send, and validate a payment initialization request."""

        canonical_payload = canonicalize_fields(
            request.signature_payload(),
            PAYMENT_INITIALIZE_SIGNATURE_FIELDS,
        )
        signature = generate_hmac_signature(
            secret_key=self._environment.merchant.secret_key,
            canonical_payload=canonical_payload,
        )
        signed_request = request.model_copy(update={"signature": signature})
        outbound_payload = signed_request.model_dump(mode="json")
        card_payload = outbound_payload["card"]
        if not isinstance(card_payload, dict):
            raise TypeError("payment request card payload must be a JSON object")
        card_payload["pan"] = signed_request.card.pan.get_secret_value()
        card_payload["cvv"] = signed_request.card.cvv.get_secret_value()
        response_payload = await self.post_json(
            "/payments/initialize",
            outbound_payload,
        )
        return PaymentInitializeResponse.model_validate(response_payload)

    async def aclose(self) -> None:
        """Close the underlying HTTPX connection pool."""

        await self._client.aclose()

    async def __aenter__(self) -> PaynkolayClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        await self.aclose()
