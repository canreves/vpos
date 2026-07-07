from __future__ import annotations

import pytest
from pydantic import SecretStr

from paynkolay_pos.callbacks import (
    CallbackSignatureVerificationError,
    canonicalize_callback_signature_payload,
    require_valid_callback_signature,
    verify_callback_signature,
)
from paynkolay_pos.models import CallbackPayload
from paynkolay_pos.testing import signed_callback_payload


@pytest.mark.callback
def test_canonicalize_callback_signature_payload_uses_provider_field_order() -> None:
    callback = CallbackPayload.model_validate(signed_callback_payload())

    assert (
        canonicalize_callback_signature_payload(callback)
        == "order-1001|txn-1001|captured|100.00|TRY|2026-07-02T09:00:00Z"
    )


@pytest.mark.callback
@pytest.mark.smoke
def test_verify_callback_signature_accepts_matching_hmac() -> None:
    callback = CallbackPayload.model_validate(signed_callback_payload())

    assert verify_callback_signature(callback, secret_key=SecretStr("callback-secret"))
    assert require_valid_callback_signature(
        callback,
        secret_key=SecretStr("callback-secret"),
    ) is callback


@pytest.mark.callback
@pytest.mark.negative
def test_verify_callback_signature_rejects_wrong_secret() -> None:
    callback = CallbackPayload.model_validate(signed_callback_payload())

    assert not verify_callback_signature(callback, secret_key=SecretStr("wrong-secret"))
    with pytest.raises(
        CallbackSignatureVerificationError,
        match="callback signature verification failed for order_id=order-1001",
    ):
        require_valid_callback_signature(callback, secret_key=SecretStr("wrong-secret"))
