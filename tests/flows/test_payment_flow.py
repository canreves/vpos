from __future__ import annotations

import pytest

from paynkolay_pos.flows import PaymentFlow
from paynkolay_pos.models import (
    PaymentInitializeRequest,
    PaymentInitializeResponse,
    PaymentStatus,
)


def valid_payment_request() -> PaymentInitializeRequest:
    return PaymentInitializeRequest.model_validate(
        {
            "merchant_id": "merchant-dev",
            "terminal_id": "terminal-dev",
            "order_id": "order-1001",
            "amount": "100.00",
            "currency": "TRY",
            "callback_url": "https://merchant-dev.example.test/callback",
            "card": {
                "brand": "visa",
                "pan": "4111111111111111",
                "expiry_month": 12,
                "expiry_year": 2030,
                "cvv": "123",
            },
            "requires_3ds": True,
            "correlation_id": "corr-1001",
        }
    )


class FakePaymentClient:
    def __init__(self, response: PaymentInitializeResponse) -> None:
        self.response = response
        self.seen_request: PaymentInitializeRequest | None = None

    async def initialize_payment(
        self,
        request: PaymentInitializeRequest,
    ) -> PaymentInitializeResponse:
        self.seen_request = request
        return self.response


@pytest.mark.api
@pytest.mark.asyncio
async def test_payment_flow_initializes_payment_through_client() -> None:
    provider_response = PaymentInitializeResponse.model_validate(
        {
            "order_id": "order-1001",
            "provider_transaction_id": "txn-1001",
            "status": "pending_3ds",
            "amount": "100.00",
            "currency": "TRY",
            "redirect_url": "https://acs.example.test/challenge/order-1001",
        }
    )
    client = FakePaymentClient(provider_response)
    request = valid_payment_request()

    response = await PaymentFlow(client).initialize(request)

    assert response is provider_response
    assert response.status is PaymentStatus.PENDING_3DS
    assert response.redirect_url == "https://acs.example.test/challenge/order-1001"
    assert client.seen_request is request
