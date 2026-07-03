"""Async HTTP client boundary for Paynkolay Sanal POS API calls."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import SecretStr

from paynkolay_pos.config import PaymentEnvironment
from paynkolay_pos.models import (
    Currency,
    PaymentInitializeRequest,
    PaymentInitializeResponse,
    TransactionStatusResponse,
)
from paynkolay_pos.security import (
    canonicalize_fields,
    generate_hmac_signature,
    generate_payment_request_hash,
)

PAYNKOLAY_PAYMENT_PATH = "/v1/Payment"
PAYNKOLAY_PAYMENT_LIST_PATH = "/Payment/PaymentList"

PAYNKOLAY_CURRENCY_NUMBERS = {
    Currency.TRY: "949",
    Currency.USD: "840",
    Currency.EUR: "978",
}

PAYMENT_INITIALIZE_SIGNATURE_FIELDS = (
    "merchant_id",
    "terminal_id",
    "order_id",
    "amount",
    "currency",
    "callback_url",
    "requires_3ds",
    "installment_count",
    "payment_channel",
    "moto",
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

    async def post_form(
        self,
        path: str,
        payload: Mapping[str, object],
    ) -> dict[str, Any]:
        """POST multipart form-data to a provider endpoint and return a JSON object body."""

        files = {
            key: (None, _form_value(value))
            for key, value in payload.items()
        }
        response = await self._client.post(path, files=files)
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
            "installment_count": request.installment_count,
            "payment_channel": request.payment_channel.value,
            "moto": request.moto,
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

    def payment_form_payload(
        self,
        request: PaymentInitializeRequest,
        *,
        success_url: str,
        fail_url: str,
        card_holder_ip: str,
        rnd: str,
        customer_key: str = "",
        merchant_customer_no: str = "",
        transaction_type: str = "SALES",
        environment: str = "API",
    ) -> dict[str, str]:
        """Build Paynkolay API v1 multipart form fields for a payment request."""

        if not success_url.startswith("https://"):
            raise ValueError("success_url must use https")
        if not fail_url.startswith("https://"):
            raise ValueError("fail_url must use https")
        if not card_holder_ip.strip():
            raise ValueError("card_holder_ip must not be empty")
        if not rnd.strip():
            raise ValueError("rnd must not be empty")

        sx = self._environment.merchant.api_key
        merchant_secret_key = self._environment.merchant.secret_key
        hash_data_v2 = generate_payment_request_hash(
            sx=sx,
            client_ref_code=request.order_id,
            amount=request.canonical_amount,
            success_url=success_url,
            fail_url=fail_url,
            rnd=rnd,
            customer_key=customer_key,
            merchant_secret_key=merchant_secret_key,
        )
        return {
            "sx": sx.get_secret_value(),
            "clientRefCode": request.order_id,
            "successUrl": success_url,
            "failUrl": fail_url,
            "amount": request.canonical_amount,
            "installmentNo": str(request.installment_count),
            "cardHolderName": request.card.card_holder,
            "month": f"{request.card.expiry_month:02d}",
            "year": str(request.card.expiry_year),
            "cvv": request.card.cvv.get_secret_value(),
            "cardNumber": request.card.pan.get_secret_value(),
            "use3D": _bool_value(request.requires_3ds),
            "transactionType": transaction_type,
            "cardHolderIP": card_holder_ip.strip(),
            "rnd": rnd,
            "hashDatav2": hash_data_v2,
            "environment": environment,
            "currencyNumber": PAYNKOLAY_CURRENCY_NUMBERS[request.currency],
            "MerchantCustomerNo": merchant_customer_no,
        }

    async def initialize_payment_form(
        self,
        request: PaymentInitializeRequest,
        *,
        success_url: str,
        fail_url: str,
        card_holder_ip: str,
        rnd: str | None = None,
        customer_key: str = "",
        merchant_customer_no: str = "",
    ) -> dict[str, Any]:
        """Send a Paynkolay API v1 payment request as multipart form-data."""

        effective_rnd = rnd if rnd is not None else datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        payload = self.payment_form_payload(
            request,
            success_url=success_url,
            fail_url=fail_url,
            card_holder_ip=card_holder_ip,
            rnd=effective_rnd,
            customer_key=customer_key,
            merchant_customer_no=merchant_customer_no,
        )
        return await self.post_form(PAYNKOLAY_PAYMENT_PATH, payload)

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


def _bool_value(value: bool) -> str:
    return "true" if value else "false"


def _form_value(value: object) -> str:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, bool):
        return _bool_value(value)
    return str(value)
