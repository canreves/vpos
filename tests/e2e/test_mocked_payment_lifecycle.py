from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from paynkolay_pos.callbacks import CallbackStore
from paynkolay_pos.clients import PaynkolayClient
from paynkolay_pos.config import RuntimeSettings
from paynkolay_pos.flows import PaymentFlow
from paynkolay_pos.models import PaymentInitializeRequest, PaymentStatus
from paynkolay_pos.scenarios import PaymentScenario
from paynkolay_pos.testing import payment_card_payload, signed_callback_payload_model


def runtime_settings() -> RuntimeSettings:
    return RuntimeSettings.model_validate(
        {
            "active_environment": "dev",
            "environments": {
                "dev": {
                    "name": "dev",
                    "base_url": "https://dev-pos.example.test",
                    "callback_base_url": "https://merchant-dev.example.test",
                    "merchant": {
                        "merchant_id": "merchant-dev",
                        "terminal_id": "terminal-dev",
                        "api_key": "api-key-dev",
                        "secret_key": "secret-dev",
                    },
                    "cards": [
                        {
                            "alias": "visa_3ds_success",
                            "brand": "visa",
                            "pan": "4111111111111111",
                            "expiry_month": 12,
                            "expiry_year": 2030,
                            "cvv": "123",
                            "requires_3ds": True,
                            "expected_otp": "123456",
                        }
                    ],
                }
            },
        }
    )


def captured_payment_scenario() -> PaymentScenario:
    return PaymentScenario.model_validate(
        {
            "scenario_id": "visa_3ds_capture",
            "title": "Visa 3DS captured payment",
            "card_alias": "visa_3ds_success",
            "amount": "100.00",
            "currency": "TRY",
            "requires_3ds": True,
            "expected_initialize_status": "pending_3ds",
            "expected_final_status": "captured",
            "tags": ("smoke", "three_ds"),
        }
    )


class MockProvider:
    def __init__(self) -> None:
        self.initialize_payload: dict[str, Any] | None = None
        self.status_calls = 0

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/payments/initialize":
            self.initialize_payload = json.loads(request.content)
            return httpx.Response(
                status_code=200,
                json={
                    "order_id": "order-1001",
                    "provider_transaction_id": "txn-1001",
                    "status": "pending_3ds",
                    "amount": "100.00",
                    "currency": "TRY",
                    "redirect_url": "https://acs.example.test/challenge/order-1001",
                },
            )

        if request.method == "GET" and request.url.path == "/payments/order-1001/status":
            self.status_calls += 1
            status = "authenticated" if self.status_calls == 1 else "captured"
            payload: dict[str, object] = {
                "order_id": "order-1001",
                "provider_transaction_id": "txn-1001",
                "status": status,
                "amount": "100.00",
                "currency": "TRY",
                "updated_at": "2026-07-02T12:00:00+03:00",
            }
            if status == "captured":
                payload["authorization_code"] = "auth-1001"
            return httpx.Response(status_code=200, json=payload)

        return httpx.Response(status_code=404, json={"error": "not_found"})


@pytest.mark.api
@pytest.mark.callback
@pytest.mark.asyncio
async def test_mocked_payment_lifecycle_confirms_final_status_and_callback() -> None:
    settings = runtime_settings()
    scenario = captured_payment_scenario()
    request = PaymentInitializeRequest.model_validate(
        scenario.payment_request_payload(
            merchant_id=settings.current.merchant.merchant_id,
            terminal_id=settings.current.merchant.terminal_id,
            callback_url=f"{settings.current.callback_base_url}/callback",
            card=payment_card_payload(),
            order_id="order-1001",
            correlation_id="corr-1001",
        )
    )
    provider = MockProvider()

    async with PaynkolayClient(
        settings.current,
        transport=httpx.MockTransport(provider),
    ) as client:
        flow = PaymentFlow(client)

        initialize_response = await flow.initialize(request)
        final_status = await flow.wait_for_final_status(
            request.order_id,
            timeout_seconds=5.0,
            poll_interval_seconds=0.01,
        )

    callback_store = CallbackStore()
    callback_store.add(
        signed_callback_payload_model(
            secret_key=SecretStr("secret-dev"),
            order_id=request.order_id,
            provider_transaction_id=final_status.provider_transaction_id,
            status=final_status.status,
            amount=f"{final_status.amount:.2f}",
            currency=final_status.currency,
        )
    )
    confirmed_callback = await flow.wait_for_verified_callback(
        request,
        final_status,
        callback_store=callback_store,
        secret_key=settings.current.merchant.secret_key,
    )

    assert initialize_response.status is scenario.expected_initialize_status
    assert final_status.status is scenario.expected_final_status
    assert confirmed_callback.status is PaymentStatus.CAPTURED
    assert provider.status_calls == 2
    assert provider.initialize_payload is not None
    assert provider.initialize_payload["order_id"] == "order-1001"
    assert provider.initialize_payload["signature"] != "<redacted>"
