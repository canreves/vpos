from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import cast

from paynkolay_pos.config import EnvironmentName, MerchantProfile, PaymentEnvironment
from paynkolay_pos.config import TestCard as ConfigTestCard
from paynkolay_pos.scenarios import PaymentScenario


def _load_uat_3ds_smoke_module() -> ModuleType:
    script_path = Path(__file__).parents[2] / "tools" / "run_uat_3ds_smoke.py"
    spec = importlib.util.spec_from_file_location("run_uat_3ds_smoke", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


UAT_3DS_SMOKE = _load_uat_3ds_smoke_module()


def test_first_3ds_scenario_skips_non_auto_success_candidates() -> None:
    scenarios = (
        _scenario("credential_denizbank_mastercard_8608_3ds_success", "denizbank_mastercard_8608"),
        _scenario("credential_yapikredi_visa_9085_3ds_success", "yapikredi_visa_9085"),
        _scenario("credential_akbank_visa_7068_3ds_success", "akbank_visa_7068"),
    )
    environment = PaymentEnvironment(
        name=EnvironmentName.DEV,
        base_url="https://local-mock.payments.invalid",
        callback_base_url="https://local-mock.callbacks.invalid",
        merchant=MerchantProfile.model_validate(
            {
                "merchant_id": "merchant",
                "terminal_id": "terminal",
                "api_key": "payment-key",
                "secret_key": "secret-key",
            }
        ),
        cards=[
            _card("denizbank_mastercard_8608"),
            _card("yapikredi_visa_9085"),
            _card("akbank_visa_7068"),
        ],
    )

    selected = cast(PaymentScenario, UAT_3DS_SMOKE._first_3ds_scenario(scenarios, environment))

    assert selected.card_alias == "akbank_visa_7068"


def test_first_3ds_scenario_accepts_dynamic_page_otp_without_configured_otp() -> None:
    scenario = _scenario(
        "credential_nkolay_dynamic_otp_visa_6111_3ds_success",
        "nkolay_dynamic_otp_visa_6111",
    )
    environment = PaymentEnvironment(
        name=EnvironmentName.DEV,
        base_url="https://local-mock.payments.invalid",
        callback_base_url="https://local-mock.callbacks.invalid",
        merchant=MerchantProfile.model_validate(
            {
                "merchant_id": "merchant",
                "terminal_id": "terminal",
                "api_key": "payment-key",
                "secret_key": "secret-key",
            }
        ),
        cards=[_card("nkolay_dynamic_otp_visa_6111", expected_otp=None)],
    )

    selected = cast(
        PaymentScenario,
        UAT_3DS_SMOKE._first_3ds_scenario((scenario,), environment),
    )

    assert selected.card_alias == "nkolay_dynamic_otp_visa_6111"
    assert UAT_3DS_SMOKE._expected_otp_from_page(environment.cards[0]) is True


def _scenario(scenario_id: str, card_alias: str) -> PaymentScenario:
    return PaymentScenario.model_validate(
        {
            "scenario_id": scenario_id,
            "title": scenario_id.replace("_", " ").title(),
            "card_alias": card_alias,
            "amount": "100.00",
            "currency": "TRY",
            "requires_3ds": True,
            "expected_initialize_status": "pending_3ds",
            "expected_final_status": "captured",
            "tags": ("three_ds",),
        }
    )


def _card(alias: str, *, expected_otp: str | None = "123456") -> ConfigTestCard:
    return ConfigTestCard.model_validate(
        {
            "alias": alias,
            "brand": "visa",
            "pan": "4111111111111111",
            "expiry_month": 12,
            "expiry_year": 2030,
            "cvv": "123",
            "requires_3ds": True,
            "expected_otp": expected_otp,
        }
    )
