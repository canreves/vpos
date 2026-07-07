from __future__ import annotations

import json
from http import HTTPStatus

import pytest
from pydantic import SecretStr

from paynkolay_pos.callbacks import (
    CallbackReceiverError,
    CallbackStore,
    accept_callback_payload,
    create_callback_handler,
    decode_callback_json,
)
from paynkolay_pos.testing import signed_callback_payload


@pytest.mark.callback
def test_accept_callback_payload_verifies_and_stores_callback() -> None:
    store = CallbackStore()
    payload = signed_callback_payload(secret_key=SecretStr("callback-secret"))

    callback = accept_callback_payload(
        payload,
        store=store,
        secret_key=SecretStr("callback-secret"),
    )

    assert callback.order_id == "order-1001"
    assert store.latest_for("order-1001") is callback


@pytest.mark.callback
@pytest.mark.negative
def test_accept_callback_payload_rejects_invalid_signature() -> None:
    store = CallbackStore()
    payload = signed_callback_payload(secret_key=SecretStr("callback-secret"))

    with pytest.raises(CallbackReceiverError, match="signature verification failed"):
        accept_callback_payload(
            payload,
            store=store,
            secret_key=SecretStr("wrong-secret"),
        )

    assert store.latest_for("order-1001") is None


@pytest.mark.callback
def test_decode_callback_json_requires_object_body() -> None:
    payload = decode_callback_json(b'{"order_id":"order-1001"}')

    assert payload == {"order_id": "order-1001"}

    with pytest.raises(CallbackReceiverError, match="valid UTF-8 JSON"):
        decode_callback_json(b"{")

    with pytest.raises(CallbackReceiverError, match="JSON object"):
        decode_callback_json(json.dumps(["not", "object"]).encode("utf-8"))


@pytest.mark.callback
def test_create_callback_handler_binds_sandbox_receiver_dependencies() -> None:
    store = CallbackStore()
    handler = create_callback_handler(
        store=store,
        secret_key=SecretStr("callback-secret"),
        callback_path="/paynkolay/callback",
    )

    assert handler.callback_store is store
    assert handler.secret_key == SecretStr("callback-secret")
    assert handler.callback_path == "/paynkolay/callback"


@pytest.mark.callback
@pytest.mark.negative
def test_create_callback_handler_rejects_relative_path() -> None:
    with pytest.raises(ValueError, match="callback_path must start with /"):
        create_callback_handler(
            store=CallbackStore(),
            secret_key=SecretStr("callback-secret"),
            callback_path="callbacks/paynkolay",
        )


@pytest.mark.callback
def test_receiver_status_codes_document_http_contract() -> None:
    assert HTTPStatus.ACCEPTED.value == 202
    assert HTTPStatus.BAD_REQUEST.value == 400
    assert HTTPStatus.NOT_FOUND.value == 404
