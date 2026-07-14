"""In-memory payment session store used by the web UI."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from paynkolay_pos.api.session_models import (
    PaymentSession,
    PaymentSessionStatus,
    ProviderRequestSummary,
    ThreeDSAutomationSummary,
    mask_pan,
    utc_now,
)
from paynkolay_pos.models import Currency, TransactionStatusResponse


class PaymentSessionAlreadyExistsError(ValueError):
    """Raised when a session order ID is already tracked."""


class PaymentSessionNotFoundError(KeyError):
    """Raised when a session order ID is not tracked."""


class PaymentSessionStore:
    """Small async in-memory store for browser payment sessions."""

    def __init__(self, *, clock: Callable[[], datetime] = utc_now) -> None:
        self._sessions: dict[str, PaymentSession] = {}
        self._lock = asyncio.Lock()
        self._clock = clock

    async def create(
        self,
        *,
        order_id: str,
        amount: Decimal,
        currency: Currency,
        pan: str,
        card_holder: str,
        requires_3ds: bool,
        installment_count: int,
    ) -> PaymentSession:
        """Create and store a sanitized payment session."""

        now = self._clock()
        session = PaymentSession(
            order_id=order_id,
            status=PaymentSessionStatus.CREATED,
            amount=amount,
            currency=currency,
            masked_pan=mask_pan(pan),
            card_holder=card_holder,
            requires_3ds=requires_3ds,
            installment_count=installment_count,
            created_at=now,
            updated_at=now,
        )
        async with self._lock:
            if session.order_id in self._sessions:
                raise PaymentSessionAlreadyExistsError(
                    f"payment session already exists for order_id={session.order_id!r}"
                )
            self._sessions[session.order_id] = session
            return session

    async def get(self, order_id: str) -> PaymentSession:
        """Return a tracked session by order ID."""

        async with self._lock:
            session = self._sessions.get(order_id)
            if session is None:
                raise PaymentSessionNotFoundError(
                    f"payment session does not exist for order_id={order_id!r}"
                )
            return session

    async def update_status(
        self,
        order_id: str,
        status: PaymentSessionStatus,
        *,
        provider_request: ProviderRequestSummary | None = None,
        provider_transaction_id: str | None = None,
        provider_response_code: str | None = None,
        provider_response_data: str | None = None,
        failure_reason: str | None = None,
    ) -> PaymentSession:
        """Update provider-facing state on a tracked session."""

        async with self._lock:
            session = self._sessions.get(order_id)
            if session is None:
                raise PaymentSessionNotFoundError(
                    f"payment session does not exist for order_id={order_id!r}"
                )

            updated = session.model_copy(
                update={
                    "status": status,
                    "provider_transaction_id": provider_transaction_id
                    if provider_transaction_id is not None
                    else session.provider_transaction_id,
                    "provider_request": provider_request
                    if provider_request is not None
                    else session.provider_request,
                    "provider_response_code": provider_response_code
                    if provider_response_code is not None
                    else session.provider_response_code,
                    "provider_response_data": provider_response_data
                    if provider_response_data is not None
                    else session.provider_response_data,
                    "failure_reason": failure_reason
                    if failure_reason is not None
                    else session.failure_reason,
                    "updated_at": self._clock(),
                }
            )
            self._sessions[order_id] = PaymentSession.model_validate(updated)
            return self._sessions[order_id]

    async def update_payment_list_status(
        self,
        order_id: str,
        status_response: TransactionStatusResponse,
    ) -> PaymentSession:
        """Store a sanitized PaymentList verification result on a tracked session."""

        async with self._lock:
            session = self._sessions.get(order_id)
            if session is None:
                raise PaymentSessionNotFoundError(
                    f"payment session does not exist for order_id={order_id!r}"
                )

            updated = session.model_copy(
                update={
                    "payment_list_status": status_response.status,
                    "payment_list_provider_transaction_id": (
                        status_response.provider_transaction_id
                    ),
                    "payment_list_authorization_code": status_response.authorization_code,
                    "payment_list_failure_code": status_response.failure_code,
                    "payment_list_updated_at": status_response.updated_at,
                    "payment_list_error": None,
                    "updated_at": self._clock(),
                }
            )
            self._sessions[order_id] = PaymentSession.model_validate(updated)
            return self._sessions[order_id]

    async def update_payment_list_error(
        self,
        order_id: str,
        error: str,
    ) -> PaymentSession:
        """Store a sanitized PaymentList verification error on a tracked session."""

        async with self._lock:
            session = self._sessions.get(order_id)
            if session is None:
                raise PaymentSessionNotFoundError(
                    f"payment session does not exist for order_id={order_id!r}"
                )

            updated = session.model_copy(
                update={
                    "payment_list_error": error,
                    "updated_at": self._clock(),
                }
            )
            self._sessions[order_id] = PaymentSession.model_validate(updated)
            return self._sessions[order_id]

    async def update_three_ds_automation(
        self,
        order_id: str,
        automation: ThreeDSAutomationSummary,
    ) -> PaymentSession:
        """Store sanitized 3DS automation evidence on a tracked session."""

        async with self._lock:
            session = self._sessions.get(order_id)
            if session is None:
                raise PaymentSessionNotFoundError(
                    f"payment session does not exist for order_id={order_id!r}"
                )

            updated = session.model_copy(
                update={
                    "three_ds_automation": automation,
                    "updated_at": self._clock(),
                }
            )
            self._sessions[order_id] = PaymentSession.model_validate(updated)
            return self._sessions[order_id]
