"""Async HTTP client boundary for Paynkolay Sanal POS API calls."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx

from paynkolay_pos.config import PaymentEnvironment
from paynkolay_pos.models import (
    PaymentInitializeRequest,
    PaymentInitializeResponse,
    TransactionStatusResponse,
)
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

    async def get_json(self, path: str) -> dict[str, Any]:
        """GET JSON from a provider endpoint and return the decoded object body."""

        response = await self._client.get(path)
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
        outbound_payload: dict[str, Any] = {
            "merchant_id": request.merchant_id,
            "terminal_id": request.terminal_id,
            "order_id": request.order_id,
            "amount": request.canonical_amount,
            "currency": request.currency.value,
            "callback_url": request.callback_url,
            "card": {
                "brand": request.card.brand.value,
                "pan": request.card.pan.get_secret_value(),
                "expiry_month": request.card.expiry_month,
                "expiry_year": request.card.expiry_year,
                "cvv": request.card.cvv.get_secret_value(),
                "card_holder": request.card.card_holder,
            },
            "requires_3ds": request.requires_3ds,
            "correlation_id": request.correlation_id,
            "signature": signature,
        }
        card_payload = outbound_payload["card"]
        if not isinstance(card_payload, dict):
            raise TypeError("payment request card payload must be a JSON object")
        response_payload = await self.post_json(
            "/payments/initialize",
            outbound_payload,
        )
        return PaymentInitializeResponse(**response_payload)

    async def get_transaction_status(self, order_id: str) -> TransactionStatusResponse:
        """Fetch and validate the provider status for one merchant order."""

        normalized_order_id = order_id.strip()
        if not normalized_order_id:
            raise ValueError("order_id must not be empty")

        response_payload = await self.get_json(
            f"/payments/{quote(normalized_order_id, safe='')}/status"
        )
        return TransactionStatusResponse(**response_payload)

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
