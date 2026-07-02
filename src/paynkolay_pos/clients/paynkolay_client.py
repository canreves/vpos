"""Async HTTP client boundary for Paynkolay Sanal POS API calls."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from paynkolay_pos.config import PaymentEnvironment


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
