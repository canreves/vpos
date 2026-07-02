from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from paynkolay_pos.models import (
    Currency,
    PaymentInitializeRequest,
    PaymentInitializeResponse,
    TransactionStatusResponse,
)


def valid_payment_request_payload() -> dict[str, object]:
    return {
        "merchant_id": "merchant-dev",
        "terminal_id": "terminal-dev",
        "order_id": "order-1001",
        "amount": "100.00",
        "currency": "TRY",
        "callback_url": "https://merchant.example.test/callbacks/paynkolay",
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


@pytest.mark.api
def test_payment_initialize_request_exposes_canonical_signature_payload() -> None:
    request = PaymentInitializeRequest.model_validate(valid_payment_request_payload())

    assert request.amount == Decimal("100.00")
    assert request.currency is Currency.TRY
    assert request.canonical_amount == "100.00"
    assert request.signature_payload() == {
        "merchant_id": "merchant-dev",
        "terminal_id": "terminal-dev",
        "order_id": "order-1001",
        "amount": "100.00",
        "currency": Currency.TRY,
        "callback_url": "https://merchant.example.test/callbacks/paynkolay",
        "requires_3ds": True,
        "correlation_id": "corr-1001",
    }


@pytest.mark.negative
def test_payment_initialize_request_rejects_non_numeric_card_data() -> None:
    payload = valid_payment_request_payload()
    card = payload["card"]
    assert isinstance(card, dict)
    card["cvv"] = "12x"

    with pytest.raises(ValidationError, match="card CVV must contain digits only"):
        PaymentInitializeRequest.model_validate(payload)


@pytest.mark.api
def test_pending_3ds_initialize_response_requires_redirect_url() -> None:
    with pytest.raises(ValidationError, match="pending_3ds responses must include redirect_url"):
        PaymentInitializeResponse.model_validate(
            {
                "order_id": "order-1001",
                "provider_transaction_id": "txn-1001",
                "status": "pending_3ds",
                "amount": "100.00",
                "currency": "TRY",
            }
        )


@pytest.mark.api
def test_transaction_status_response_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValidationError, match="updated_at must include timezone information"):
        TransactionStatusResponse.model_validate(
            {
                "order_id": "order-1001",
                "provider_transaction_id": "txn-1001",
                "status": "captured",
                "amount": "100.00",
                "currency": "TRY",
                "updated_at": datetime(2026, 7, 2, 12, 0, 0),
                "authorization_code": "auth-123",
            }
        )

    response = TransactionStatusResponse.model_validate(
        {
            "order_id": "order-1001",
            "provider_transaction_id": "txn-1001",
            "status": "captured",
            "amount": "100.00",
            "currency": "TRY",
            "updated_at": datetime(2026, 7, 2, 12, 0, 0, tzinfo=UTC),
            "authorization_code": "auth-123",
        }
    )

    assert response.updated_at == datetime(2026, 7, 2, 12, 0, 0, tzinfo=UTC)
