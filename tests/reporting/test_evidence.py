from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import SecretStr

from paynkolay_pos.reporting import attach_json_evidence, evidence_json, sanitize_evidence
from paynkolay_pos.testing import payment_initialize_request, signed_callback_payload


@pytest.mark.api
def test_sanitize_evidence_redacts_sensitive_payment_fields() -> None:
    payload: dict[str, object] = {
        "merchant_id": "merchant-dev",
        "api_key": "api-key-dev",
        "cancel_refund_api_key": "cancel-refund-api-key-dev",
        "secret_key": SecretStr("secret-dev"),
        "signature": "abc123",
        "card": {
            "pan": "4111111111111111",
            "cvv": "123",
            "expiry_month": 12,
        },
        "three_ds": {"otp": "123456"},
    }

    sanitized = sanitize_evidence(payload)

    assert sanitized == {
        "merchant_id": "merchant-dev",
        "api_key": "<redacted>",
        "cancel_refund_api_key": "<redacted>",
        "secret_key": "<redacted>",
        "signature": "<redacted>",
        "card": {
            "pan": "************1111",
            "cvv": "<redacted>",
            "expiry_month": 12,
        },
        "three_ds": {"otp": "<redacted>"},
    }


@pytest.mark.api
def test_sanitize_evidence_redacts_paynkolay_form_payload_fields() -> None:
    payload: dict[str, object] = {
        "sx": "payment-sx-private",
        "clientRefCode": "order-1001",
        "cardNumber": "4111111111111111",
        "cvv": "123",
        "hashData": "legacy-hash",
        "hashDatav2": "sha512-base64-hash",
        "amount": "100.00",
    }

    body = evidence_json(payload)
    decoded = json.loads(body)

    assert decoded["sx"] == "<redacted>"
    assert decoded["cardNumber"] == "************1111"
    assert decoded["cvv"] == "<redacted>"
    assert decoded["hashData"] == "<redacted>"
    assert decoded["hashDatav2"] == "<redacted>"
    assert "payment-sx-private" not in body
    assert "4111111111111111" not in body
    assert "sha512-base64-hash" not in body


@pytest.mark.api
def test_evidence_json_serializes_models_and_callback_payloads_without_secrets() -> None:
    payment_request = payment_initialize_request()
    callback_payload = signed_callback_payload()

    body = evidence_json(
        {
            "request": payment_request,
            "callback": callback_payload,
        }
    )

    assert json.loads(body)["callback"]["signature"] == "<redacted>"
    assert "4111111111111111" not in body
    assert "123456" not in body
    assert "callback-secret" not in body


class FakeAttachmentType:
    JSON = "application/json"


class FakeAllure:
    attachment_type = FakeAttachmentType

    def __init__(self) -> None:
        self.attachments: list[dict[str, Any]] = []

    def attach(self, body: str, *, name: str, attachment_type: Any) -> None:
        self.attachments.append(
            {
                "body": body,
                "name": name,
                "attachment_type": attachment_type,
            }
        )


@pytest.mark.api
def test_attach_json_evidence_attaches_sanitized_body_to_allure() -> None:
    fake_allure = FakeAllure()

    body = attach_json_evidence(
        "payment request",
        {"card": {"pan": "5555444433332222", "cvv": "999"}},
        allure_module=fake_allure,
    )

    assert fake_allure.attachments == [
        {
            "body": body,
            "name": "payment request",
            "attachment_type": "application/json",
        }
    ]
    assert "5555444433332222" not in body
    assert "999" not in body
    assert "************2222" in body
