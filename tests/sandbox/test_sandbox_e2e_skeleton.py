from __future__ import annotations

import os
from datetime import datetime
from uuid import uuid4

import pytest

from paynkolay_pos.clients import PaynkolayClient
from paynkolay_pos.config import EnvironmentName, PaymentEnvironment, load_runtime_settings
from paynkolay_pos.config import (
    TestCard as ConfigTestCard,
)
from paynkolay_pos.models import PaymentInitializeRequest
from paynkolay_pos.scenarios import PaymentScenario, load_payment_scenario_catalog_from_env

pytestmark = [pytest.mark.sandbox, pytest.mark.live_e2e]

LIVE_SANDBOX_FLOW_STEPS = (
    "build payment request from private scenario and card",
    "send Paynkolay /v1/Payment form request",
    "complete 3DS challenge when the scenario requires 3DS",
    "verify transaction through /Payment/PaymentList",
    "wait for and verify callback when callback delivery is enabled",
    "attach sanitized request, response, status, and callback evidence",
)


def _sandbox_config_available() -> bool:
    return bool(os.getenv("PAYNKOLAY_CONFIG_FILE"))


pytestmark.append(
    pytest.mark.skipif(
        not _sandbox_config_available(),
        reason="PAYNKOLAY_CONFIG_FILE is required for sandbox skeleton tests",
    )
)


def test_sandbox_runtime_config_is_loadable_and_not_placeholder() -> None:
    settings = load_runtime_settings()
    environment = settings.current

    assert environment.base_url.startswith("https://")
    assert environment.callback_base_url.startswith("https://")
    assert environment.cards
    assert "replace-with" not in environment.merchant.merchant_id
    assert "replace-with" not in environment.merchant.terminal_id
    assert "replace-with" not in environment.merchant.api_key.get_secret_value()
    assert "replace-with" not in environment.merchant.secret_key.get_secret_value()


def test_sandbox_scenario_catalog_matches_configured_cards() -> None:
    settings = load_runtime_settings()
    catalog = load_payment_scenario_catalog_from_env()
    configured_aliases = {card.alias for card in settings.current.cards}

    missing_aliases = sorted(
        {
            scenario.card_alias
            for scenario in catalog.scenarios
            if scenario.card_alias not in configured_aliases
        }
    )

    assert missing_aliases == []


def test_sandbox_payment_form_payload_can_be_built_without_network() -> None:
    settings = load_runtime_settings()
    environment = settings.current
    catalog = load_payment_scenario_catalog_from_env()
    scenario = catalog.scenarios[0]
    card = _card_for_alias(environment, scenario.card_alias)
    request = _payment_request_for(environment, scenario, card)

    client = PaynkolayClient(environment)
    success_url = environment.callback_base_url
    fail_url = environment.callback_base_url
    if environment.name is not EnvironmentName.UAT:
        success_url = f"{environment.callback_base_url}/paynkolay/success"
        fail_url = f"{environment.callback_base_url}/paynkolay/fail"
    payload = client.payment_form_payload(
        request,
        success_url=success_url,
        fail_url=fail_url,
        card_holder_ip="127.0.0.1",
        rnd=datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
    )

    assert payload["clientRefCode"] == request.order_id
    assert payload["amount"] == scenario.canonical_amount
    assert payload["use3D"] == str(scenario.requires_3ds).lower()
    assert payload["hashDatav2"]


@pytest.mark.skipif(
    os.getenv("PAYNKOLAY_ENABLE_LIVE_E2E") != "1",
    reason="set PAYNKOLAY_ENABLE_LIVE_E2E=1 to allow real sandbox network calls",
)
@pytest.mark.asyncio
async def test_live_sandbox_payment_flow_placeholder() -> None:
    """Guarded placeholder for the real provider call sequence."""

    pytest.skip(
        "wire this test after sandbox endpoint contract, callback URL, real test cards, "
        f"and 3DS selectors are confirmed; planned steps: {LIVE_SANDBOX_FLOW_STEPS}"
    )


def test_live_sandbox_flow_steps_document_remaining_provider_work() -> None:
    assert LIVE_SANDBOX_FLOW_STEPS == (
        "build payment request from private scenario and card",
        "send Paynkolay /v1/Payment form request",
        "complete 3DS challenge when the scenario requires 3DS",
        "verify transaction through /Payment/PaymentList",
        "wait for and verify callback when callback delivery is enabled",
        "attach sanitized request, response, status, and callback evidence",
    )


def _card_for_alias(environment: PaymentEnvironment, alias: str) -> ConfigTestCard:
    for card in environment.cards:
        if card.alias == alias:
            return card
    raise AssertionError(f"card alias not configured for sandbox run: {alias}")


def _payment_request_for(
    environment: PaymentEnvironment,
    scenario: PaymentScenario,
    card: ConfigTestCard,
) -> PaymentInitializeRequest:
    return PaymentInitializeRequest.model_validate(
        scenario.payment_request_payload(
            merchant_id=environment.merchant.merchant_id,
            terminal_id=environment.merchant.terminal_id,
            callback_url=(
                environment.callback_base_url
                if environment.name is EnvironmentName.UAT
                else f"{environment.callback_base_url}/callbacks/paynkolay"
            ),
            card={
                "brand": card.brand.value,
                "pan": card.pan.get_secret_value(),
                "expiry_month": card.expiry_month,
                "expiry_year": card.expiry_year,
                "cvv": card.cvv.get_secret_value(),
            },
            order_id=f"sandbox-{scenario.scenario_id}-{uuid4().hex[:12]}",
            correlation_id=f"sandbox-{uuid4().hex}",
        )
    )
