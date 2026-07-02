from __future__ import annotations

import pytest
from pydantic import ValidationError

from paynkolay_pos.models import PaymentChannel, PaymentStatus
from paynkolay_pos.scenarios import PaymentScenario, PaymentScenarioCatalog
from paynkolay_pos.testing import payment_card_payload


def payment_scenario(**overrides: object) -> PaymentScenario:
    payload: dict[str, object] = {
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
    payload.update(overrides)
    return PaymentScenario.model_validate(payload)


@pytest.mark.api
def test_payment_scenario_builds_payment_request_payload() -> None:
    scenario = payment_scenario(installment_count=3)

    payload = scenario.payment_request_payload(
        merchant_id="merchant-dev",
        terminal_id="terminal-dev",
        callback_url="https://merchant.example.test/callback",
        card=payment_card_payload(),
        order_id="order-1001",
        correlation_id="corr-1001",
    )

    assert scenario.canonical_amount == "100.00"
    assert payload == {
        "merchant_id": "merchant-dev",
        "terminal_id": "terminal-dev",
        "order_id": "order-1001",
        "amount": "100.00",
        "currency": "TRY",
        "callback_url": "https://merchant.example.test/callback",
        "card": payment_card_payload(),
        "requires_3ds": True,
        "installment_count": 3,
        "payment_channel": PaymentChannel.E_COMMERCE,
        "moto": False,
        "correlation_id": "corr-1001",
    }


@pytest.mark.api
def test_payment_scenario_catalog_indexes_unique_scenarios() -> None:
    captured = payment_scenario()
    moto = payment_scenario(
        scenario_id="moto_capture",
        title="MoTo captured payment",
        card_alias="visa_moto_success",
        requires_3ds=False,
        expected_initialize_status=PaymentStatus.AUTHORIZED,
        payment_channel=PaymentChannel.MOTO,
        moto=True,
        tags=("moto",),
    )
    catalog = PaymentScenarioCatalog(scenarios=(captured, moto))

    assert catalog.ids() == ("visa_3ds_capture", "moto_capture")
    assert catalog.get("moto_capture") is moto
    assert catalog.tagged("three_ds") == (captured,)
    assert catalog.tagged("missing") == ()


@pytest.mark.negative
def test_payment_scenario_catalog_rejects_duplicate_ids() -> None:
    with pytest.raises(ValidationError, match="scenario_id values must be unique"):
        PaymentScenarioCatalog(scenarios=(payment_scenario(), payment_scenario()))


@pytest.mark.negative
def test_payment_scenario_rejects_inconsistent_metadata() -> None:
    with pytest.raises(ValidationError, match="scenario tags must be unique"):
        payment_scenario(tags=("smoke", "smoke"))

    with pytest.raises(ValidationError, match="moto scenarios must not require 3DS"):
        payment_scenario(
            requires_3ds=True,
            payment_channel=PaymentChannel.MOTO,
            moto=True,
        )
