from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from paynkolay_pos.models import (
    Currency,
    PaymentChannel,
    PaymentInitializeRequest,
    PaymentInitializeResponse,
    TransactionStatusResponse,
)
from paynkolay_pos.testing import payment_initialize_request_payload


@pytest.mark.api
def test_payment_initialize_request_exposes_canonical_signature_payload() -> None:
    request = PaymentInitializeRequest.model_validate(
        payment_initialize_request_payload(
            callback_url="https://merchant.example.test/callbacks/paynkolay"
        )
    )

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
        "installment_count": 1,
        "payment_channel": PaymentChannel.E_COMMERCE,
        "moto": False,
        "correlation_id": "corr-1001",
    }


@pytest.mark.api
def test_payment_initialize_request_models_installment_and_moto_scenarios() -> None:
    installment_request = PaymentInitializeRequest.model_validate(
        payment_initialize_request_payload(installment_count=3)
    )
    moto_request = PaymentInitializeRequest.model_validate(
        payment_initialize_request_payload(
            requires_3ds=False,
            payment_channel="moto",
            moto=True,
        )
    )

    assert installment_request.installment_count == 3
    assert installment_request.payment_channel is PaymentChannel.E_COMMERCE
    assert installment_request.moto is False
    assert moto_request.requires_3ds is False
    assert moto_request.payment_channel is PaymentChannel.MOTO
    assert moto_request.moto is True


@pytest.mark.negative
def test_payment_initialize_request_requires_consistent_moto_metadata() -> None:
    with pytest.raises(ValidationError, match="moto payments must use payment_channel=moto"):
        PaymentInitializeRequest.model_validate(payment_initialize_request_payload(moto=True))

    with pytest.raises(ValidationError, match="payment_channel=moto requires moto=true"):
        PaymentInitializeRequest.model_validate(
            payment_initialize_request_payload(payment_channel="moto")
        )


@pytest.mark.negative
def test_payment_initialize_request_rejects_non_numeric_card_data() -> None:
    payload = payment_initialize_request_payload()
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
