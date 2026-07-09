"""Tests for the isolated mock error interceptor."""

from __future__ import annotations

import pytest

from paynkolay_pos.flows.error_interceptor import (
    DEFAULT_TRIGGER_CVVS,
    MockErrorInterceptor,
)
from paynkolay_pos.models import (
    PaymentInitializeRequest,
    PaymentInitializeResponse,
    PaymentStatus,
    TransactionStatusResponse,
)
from paynkolay_pos.scenarios.error_matrix import load_error_matrix
from paynkolay_pos.testing import payment_initialize_request


class RecordingInner:
    """A stand-in payment client that records whether it was called."""

    def __init__(self) -> None:
        self.initialize_calls = 0

    async def initialize_payment(
        self, request: PaymentInitializeRequest
    ) -> PaymentInitializeResponse:
        self.initialize_calls += 1
        return PaymentInitializeResponse.model_validate(
            {
                "order_id": request.order_id,
                "status": PaymentStatus.PENDING_3DS,
                "amount": request.canonical_amount,
                "currency": request.currency,
                "redirect_url": f"https://acs.example.test/challenge/{request.order_id}",
            }
        )

    async def get_transaction_status(self, order_id: str) -> TransactionStatusResponse:
        raise AssertionError("get_transaction_status should not be called here")


def _request_with_cvv(cvv: str) -> PaymentInitializeRequest:
    return payment_initialize_request(
        card={
            "brand": "visa",
            "pan": "4111111111111111",
            "expiry_month": 12,
            "expiry_year": 2030,
            "cvv": cvv,
        }
    )


@pytest.mark.negative
@pytest.mark.asyncio
@pytest.mark.parametrize("cvv, scenario", sorted(DEFAULT_TRIGGER_CVVS.items()))
async def test_trigger_cvv_returns_matrix_failure(cvv: str, scenario: str) -> None:
    """Each trigger CVV returns the failure defined in the CSV matrix."""

    matrix = load_error_matrix()
    inner = RecordingInner()
    interceptor = MockErrorInterceptor(inner)

    response = await interceptor.initialize_payment(_request_with_cvv(cvv))

    expected = matrix[scenario]
    assert response.status is PaymentStatus.FAILED
    assert response.failure_code == expected.expected_error_code
    assert response.failure_reason == expected.expected_error_message
    assert inner.initialize_calls == 0


@pytest.mark.negative
@pytest.mark.asyncio
async def test_non_trigger_cvv_delegates_to_inner() -> None:
    """A normal CVV is passed through to the wrapped client unchanged."""

    inner = RecordingInner()
    interceptor = MockErrorInterceptor(inner)

    response = await interceptor.initialize_payment(_request_with_cvv("123"))

    assert response.status is PaymentStatus.PENDING_3DS
    assert inner.initialize_calls == 1
