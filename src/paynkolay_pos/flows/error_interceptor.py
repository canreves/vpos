"""Isolated mock interceptor that returns matrix-defined failures for trigger inputs.

This wraps a real payment client without modifying it. When an incoming request
carries a known trigger CVV, the interceptor returns the failure defined in the
CSV error matrix instead of calling the provider. Otherwise it delegates to the
wrapped client unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping

from paynkolay_pos.flows.payment_flow import SupportsPaymentInitialization
from paynkolay_pos.models import (
    PaymentInitializeRequest,
    PaymentInitializeResponse,
    PaymentStatus,
    TransactionStatusResponse,
)
from paynkolay_pos.scenarios.error_matrix import ErrorMatrixCase, load_error_matrix

# Maps a "magic" trigger CVV to a scenario name in the error matrix.
DEFAULT_TRIGGER_CVVS: Mapping[str, str] = {
    "501": "wrong_otp",
    "502": "expired_card",
    "503": "insufficient_funds",
}


class MockErrorInterceptor:
    """Wrap a payment client and short-circuit known error-trigger requests."""

    def __init__(
        self,
        inner: SupportsPaymentInitialization,
        *,
        matrix: Mapping[str, ErrorMatrixCase] | None = None,
        trigger_cvvs: Mapping[str, str] = DEFAULT_TRIGGER_CVVS,
    ) -> None:
        self._inner = inner
        self._matrix = matrix if matrix is not None else load_error_matrix()
        self._trigger_cvvs = trigger_cvvs

    async def initialize_payment(
        self,
        request: PaymentInitializeRequest,
    ) -> PaymentInitializeResponse:
        """Return a mock failure for trigger requests; otherwise delegate."""

        case = self._match(request)
        if case is None:
            return await self._inner.initialize_payment(request)
        return self._failure_response(request, case)

    async def get_transaction_status(self, order_id: str) -> TransactionStatusResponse:
        """Delegate status lookups to the wrapped client unchanged."""

        return await self._inner.get_transaction_status(order_id)

    def _match(self, request: PaymentInitializeRequest) -> ErrorMatrixCase | None:
        cvv = request.card.cvv.get_secret_value()
        scenario = self._trigger_cvvs.get(cvv)
        if scenario is None:
            return None
        if scenario not in self._matrix:
            raise KeyError(f"trigger scenario not in error matrix: {scenario}")
        return self._matrix[scenario]

    def _failure_response(
        self,
        request: PaymentInitializeRequest,
        case: ErrorMatrixCase,
    ) -> PaymentInitializeResponse:
        return PaymentInitializeResponse.model_validate(
            {
                "order_id": request.order_id,
                "status": PaymentStatus.FAILED,
                "amount": request.canonical_amount,
                "currency": request.currency,
                "failure_code": case.expected_error_code,
                "failure_reason": case.expected_error_message,
            }
        )
