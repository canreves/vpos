from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from paynkolay_pos.models import CallbackPayload, Currency, PaymentStatus
from paynkolay_pos.testing import callback_payload


@pytest.mark.callback
def test_callback_payload_normalizes_timestamp_and_signature_payload() -> None:
    callback = CallbackPayload.model_validate(callback_payload())

    assert callback.status is PaymentStatus.CAPTURED
    assert callback.amount == Decimal("100.00")
    assert callback.currency is Currency.TRY
    assert callback.received_at == datetime(2026, 7, 2, 9, 0, 0, tzinfo=UTC)
    assert callback.signature_payload() == {
        "order_id": "order-1001",
        "provider_transaction_id": "txn-1001",
        "status": PaymentStatus.CAPTURED,
        "amount": "100.00",
        "currency": Currency.TRY,
        "received_at": "2026-07-02T09:00:00Z",
    }


@pytest.mark.callback
@pytest.mark.negative
def test_callback_payload_requires_timezone_aware_received_at() -> None:
    payload = callback_payload()
    payload["received_at"] = datetime(2026, 7, 2, 12, 0, 0)

    with pytest.raises(ValidationError, match="received_at must include timezone information"):
        CallbackPayload.model_validate(payload)


@pytest.mark.callback
@pytest.mark.negative
def test_callback_payload_requires_status_specific_evidence() -> None:
    captured_payload = callback_payload()
    captured_payload.pop("authorization_code")

    with pytest.raises(ValidationError, match="approved callbacks must include authorization_code"):
        CallbackPayload.model_validate(captured_payload)

    failed_payload = callback_payload()
    failed_payload["status"] = "failed"
    failed_payload.pop("authorization_code")

    with pytest.raises(ValidationError, match="failed callbacks must include failure_code"):
        CallbackPayload.model_validate(failed_payload)
