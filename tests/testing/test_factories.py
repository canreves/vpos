from __future__ import annotations

import pytest
from pydantic import SecretStr

from paynkolay_pos.callbacks import verify_callback_signature
from paynkolay_pos.models import Currency, PaymentStatus
from paynkolay_pos.testing import (
    callback_payload_model,
    payment_initialize_request,
    signed_callback_payload_model,
    transaction_status_response,
)


@pytest.mark.api
def test_payment_initialize_request_factory_builds_valid_3ds_request() -> None:
    request = payment_initialize_request(order_id="order-2002", amount="250.50")

    assert request.order_id == "order-2002"
    assert request.canonical_amount == "250.50"
    assert request.currency is Currency.TRY
    assert request.requires_3ds is True


@pytest.mark.api
def test_transaction_status_factory_adds_status_specific_evidence() -> None:
    captured = transaction_status_response(PaymentStatus.CAPTURED)
    failed = transaction_status_response(PaymentStatus.FAILED)

    assert captured.authorization_code == "auth-1001"
    assert failed.failure_code == "issuer_declined"


@pytest.mark.callback
def test_callback_factories_build_unsigned_and_signed_callbacks() -> None:
    unsigned = callback_payload_model(status=PaymentStatus.AUTHORIZED)
    signed = signed_callback_payload_model(secret_key=SecretStr("callback-secret"))

    assert unsigned.status is PaymentStatus.AUTHORIZED
    assert unsigned.authorization_code == "auth-1001"
    assert verify_callback_signature(signed, secret_key=SecretStr("callback-secret"))
