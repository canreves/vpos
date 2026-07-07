"""Transient in-memory store for provider 3D Secure form payloads."""

from __future__ import annotations

import asyncio


class ThreeDSFormNotFoundError(KeyError):
    """Raised when a 3DS form payload is not tracked for an order."""


class ThreeDSFormStore:
    """Small async in-memory store for raw provider 3DS form payloads."""

    def __init__(self) -> None:
        self._forms: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def put(self, order_id: str, payload: str) -> None:
        """Store a raw provider 3DS form payload by order ID."""

        normalized_order_id = order_id.strip()
        if not normalized_order_id:
            raise ValueError("order_id must not be empty")
        if not payload.strip():
            raise ValueError("3DS form payload must not be empty")

        async with self._lock:
            self._forms[normalized_order_id] = payload

    async def get(self, order_id: str) -> str:
        """Return a raw provider 3DS form payload by order ID."""

        normalized_order_id = order_id.strip()
        async with self._lock:
            payload = self._forms.get(normalized_order_id)
            if payload is None:
                raise ThreeDSFormNotFoundError(
                    f"3DS form payload does not exist for order_id={normalized_order_id!r}"
                )
            return payload

