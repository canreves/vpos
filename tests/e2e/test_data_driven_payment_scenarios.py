from __future__ import annotations

import json
import os
from hashlib import sha1
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import pytest

from paynkolay_pos.clients import PaynkolayClient
from paynkolay_pos.config import PaymentEnvironment, RuntimeSettings
from paynkolay_pos.config import TestCard as ConfigTestCard
from paynkolay_pos.flows import PaymentFlow
from paynkolay_pos.models import PaymentInitializeRequest, PaymentStatus
from paynkolay_pos.scenarios import (
    PaymentScenario,
    load_payment_scenario_catalog_from_env,
)

SCENARIO_CATALOG = load_payment_scenario_catalog_from_env()


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "scenario" in metafunc.fixturenames:
        metafunc.parametrize(
            "scenario",
            SCENARIO_CATALOG.scenarios,
            ids=SCENARIO_CATALOG.ids(),
        )


def runtime_settings() -> RuntimeSettings:
    config_file = os.getenv("PAYNKOLAY_CONFIG_FILE")
    if config_file:
        return RuntimeSettings.model_validate_json(
            Path(config_file).expanduser().read_text(encoding="utf-8")
        )

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
                        card_config("visa_3ds_success", requires_3ds=True),
                        card_config("visa_installment_success", requires_3ds=True),
                        card_config("visa_3ds_declined", requires_3ds=True),
                        card_config("visa_moto_success", requires_3ds=False),
                    ],
                }
            },
        }
    )


def card_config(alias: str, *, requires_3ds: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "alias": alias,
        "brand": "visa",
        "pan": "4111111111111111",
        "expiry_month": 12,
        "expiry_year": 2030,
        "cvv": "123",
        "requires_3ds": requires_3ds,
    }
    if requires_3ds:
        payload["expected_otp"] = "123456"
    return payload


class ScenarioMockProvider:
    def __init__(self, scenario: PaymentScenario, *, order_id: str) -> None:
        self._scenario = scenario
        self._order_id = order_id
        self.initialize_payload: dict[str, Any] | None = None
        self.status_calls = 0

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/payments/initialize":
            self.initialize_payload = json.loads(request.content)
            return httpx.Response(status_code=200, json=self._initialize_response())

        expected_status_path = f"/payments/{quote(self._order_id, safe='')}/status"
        if request.method == "GET" and request.url.path == expected_status_path:
            self.status_calls += 1
            return httpx.Response(status_code=200, json=self._status_response())

        return httpx.Response(status_code=404, json={"error": "not_found"})

    def _initialize_response(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "order_id": self._order_id,
            "provider_transaction_id": self.provider_transaction_id,
            "status": self._scenario.expected_initialize_status.value,
            "amount": self._scenario.canonical_amount,
            "currency": self._scenario.currency.value,
        }
        if self._scenario.expected_initialize_status is PaymentStatus.PENDING_3DS:
            payload["redirect_url"] = f"https://acs.example.test/challenge/{self._order_id}"
        if self._scenario.expected_initialize_status is PaymentStatus.FAILED:
            payload["failure_code"] = "issuer_declined"
            payload["failure_reason"] = "Issuer declined"
        return payload

    def _status_response(self) -> dict[str, object]:
        final_status = self._scenario.expected_final_status
        payload: dict[str, object] = {
            "order_id": self._order_id,
            "provider_transaction_id": self.provider_transaction_id,
            "status": final_status.value,
            "amount": self._scenario.canonical_amount,
            "currency": self._scenario.currency.value,
            "updated_at": "2026-07-03T09:45:00+03:00",
        }
        if final_status in {PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED}:
            payload["authorization_code"] = f"auth-{self._scenario.scenario_id}"
        if final_status is PaymentStatus.FAILED:
            payload["failure_code"] = "issuer_declined"
        return payload

    @property
    def provider_transaction_id(self) -> str:
        return f"txn-{self._scenario.scenario_id}"


@pytest.mark.api
@pytest.mark.scenario
@pytest.mark.asyncio
async def test_catalog_scenario_executes_against_mocked_provider(
    scenario: PaymentScenario,
) -> None:
    settings = runtime_settings()
    environment = settings.current
    card = card_payload_for(environment, scenario.card_alias)
    order_id = order_id_for(scenario)
    request = PaymentInitializeRequest.model_validate(
        scenario.payment_request_payload(
            merchant_id=environment.merchant.merchant_id,
            terminal_id=environment.merchant.terminal_id,
            callback_url=f"{environment.callback_base_url}/callback",
            card=card,
            order_id=order_id,
            correlation_id=f"corr-{scenario.scenario_id}",
        )
    )
    provider = ScenarioMockProvider(scenario, order_id=order_id)

    async with PaynkolayClient(
        environment,
        transport=httpx.MockTransport(provider),
    ) as client:
        flow = PaymentFlow(client)
        initialize_response = await flow.initialize(request)
        final_status = await flow.wait_for_final_status(
            request.order_id,
            timeout_seconds=1.0,
            poll_interval_seconds=0.01,
        )

    assert initialize_response.status is scenario.expected_initialize_status
    assert final_status.status is scenario.expected_final_status
    assert final_status.amount == scenario.amount
    assert final_status.currency is scenario.currency
    assert provider.status_calls == 1
    assert provider.initialize_payload is not None
    assert provider.initialize_payload["order_id"] == order_id
    assert provider.initialize_payload["installment_count"] == scenario.installment_count
    assert provider.initialize_payload["requires_3ds"] is scenario.requires_3ds
    assert provider.initialize_payload["moto"] is scenario.moto


def order_id_for(scenario: PaymentScenario) -> str:
    digest = sha1(scenario.scenario_id.encode("utf-8")).hexdigest()[:12]
    return f"order-{digest}"


def card_payload_for(environment: PaymentEnvironment, alias: str) -> dict[str, object]:
    for card in environment.cards:
        if card.alias == alias:
            return card_payload(card)
    # Generated private catalogues can reference generated card aliases; this mocked
    # provider test only needs schema-valid card details to exercise scenario flow.
    return {
        "brand": "visa",
        "pan": "4111111111111111",
        "expiry_month": 12,
        "expiry_year": 2030,
        "cvv": "123",
    }


def card_payload(card: ConfigTestCard) -> dict[str, object]:
    return {
        "brand": card.brand.value,
        "pan": card.pan.get_secret_value(),
        "expiry_month": card.expiry_month,
        "expiry_year": card.expiry_year,
        "cvv": card.cvv.get_secret_value(),
    }
