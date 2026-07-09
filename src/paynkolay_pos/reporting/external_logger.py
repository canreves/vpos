"""External payment event logging with sensitive-data sanitization."""

from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum
from typing import Protocol

import httpx
from pydantic import BaseModel, Field

from paynkolay_pos.api.session_models import PaymentSession
from paynkolay_pos.reporting.evidence import sanitize_evidence


class PaymentLogEventType(StrEnum):
    """Browser payment workflow events sent to an external log endpoint."""

    PAYMENT_INITIALIZED = "payment_initialized"
    THREE_DS_REQUIRED = "three_ds_required"
    THREE_DS_RENDERED = "three_ds_rendered"
    PAYMENT_SUCCESS_RETURNED = "payment_success_returned"
    PAYMENT_FAIL_RETURNED = "payment_fail_returned"
    CALLBACK_RECEIVED = "callback_received"


class PaymentLogEvent(BaseModel):
    """Sanitized external log event payload."""

    event: PaymentLogEventType
    order_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    amount: str = Field(min_length=1)
    currency: str = Field(min_length=3, max_length=3)
    masked_pan: str = Field(min_length=8)
    requires_3ds: bool
    provider_transaction_id: str | None = None
    failure_reason: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @classmethod
    def from_session(
        cls,
        *,
        event: PaymentLogEventType,
        session: PaymentSession,
        metadata: Mapping[str, object] | None = None,
    ) -> PaymentLogEvent:
        """Build an external log event from sanitized session state."""

        sanitized_metadata = sanitize_evidence(dict(metadata or {}))
        if not isinstance(sanitized_metadata, dict):
            sanitized_metadata = {}
        return cls(
            event=event,
            order_id=session.order_id,
            status=session.status.value,
            amount=session.canonical_amount,
            currency=session.currency.value,
            masked_pan=session.masked_pan,
            requires_3ds=session.requires_3ds,
            provider_transaction_id=session.provider_transaction_id,
            failure_reason=session.failure_reason,
            metadata=sanitized_metadata,
        )


class SupportsExternalPaymentLogger(Protocol):
    """Behavior required by routes for external payment logging."""

    async def log(self, event: PaymentLogEvent) -> None:
        """Send a sanitized event to an external system."""


class DisabledExternalPaymentLogger:
    """No-op logger used when no external endpoint is configured."""

    async def log(self, event: PaymentLogEvent) -> None:
        return None


class HttpExternalPaymentLogger:
    """HTTP implementation for external payment event logging."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        timeout_seconds: float = 5.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not endpoint_url.startswith(("https://", "http://")):
            raise ValueError("external log endpoint must use http or https")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        self._endpoint_url = endpoint_url
        self._timeout_seconds = timeout_seconds
        self._client = client
        self._owns_client = client is None

    async def log(self, event: PaymentLogEvent) -> None:
        client = self._client
        if client is None:
            client = httpx.AsyncClient(timeout=self._timeout_seconds)
            self._client = client
        response = await client.post(
            self._endpoint_url,
            json=event.model_dump(mode="json"),
        )
        response.raise_for_status()

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None


def external_logger_from_env() -> SupportsExternalPaymentLogger:
    """Create an external logger from environment variables."""

    endpoint_url = os.getenv("PAYNKOLAY_EXTERNAL_LOG_URL", "").strip()
    if not endpoint_url:
        return DisabledExternalPaymentLogger()

    timeout_value = os.getenv("PAYNKOLAY_EXTERNAL_LOG_TIMEOUT_SECONDS", "5").strip()
    try:
        timeout_seconds = float(timeout_value)
    except ValueError:
        timeout_seconds = 5.0
    return HttpExternalPaymentLogger(
        endpoint_url=endpoint_url,
        timeout_seconds=timeout_seconds,
    )
