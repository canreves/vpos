from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from paynkolay_pos.config import EnvironmentName, RuntimeSettings, load_runtime_settings


def valid_settings_payload() -> dict[str, object]:
    return {
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
                    "cancel_refund_api_key": "cancel-refund-api-key-dev",
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
            },
            "uat": {
                "name": "uat",
                "base_url": "https://uat-pos.example.test",
                "callback_base_url": "https://merchant-uat.example.test",
                "merchant": {
                    "merchant_id": "merchant-uat",
                    "terminal_id": "terminal-uat",
                    "api_key": "api-key-uat",
                    "secret_key": "secret-uat",
                },
                "cards": [
                    {
                        "alias": "mastercard_non_3ds_success",
                        "brand": "mastercard",
                        "pan": "5555555555554444",
                        "expiry_month": 11,
                        "expiry_year": 2031,
                        "cvv": "456",
                        "requires_3ds": False,
                    }
                ],
            },
        },
    }


@pytest.mark.config
def test_runtime_settings_selects_active_environment() -> None:
    settings = RuntimeSettings.model_validate(valid_settings_payload())

    assert settings.active_environment is EnvironmentName.DEV
    assert settings.current.name is EnvironmentName.DEV
    assert settings.current.merchant.merchant_id == "merchant-dev"
    assert settings.current.merchant.cancel_refund_api_key is not None
    assert (
        settings.current.merchant.cancel_refund_api_key.get_secret_value()
        == "cancel-refund-api-key-dev"
    )
    assert settings.current.cards[0].alias == "visa_3ds_success"


@pytest.mark.config
def test_runtime_settings_rejects_3ds_card_without_otp() -> None:
    payload = valid_settings_payload()
    environments = payload["environments"]
    assert isinstance(environments, dict)
    dev = environments["dev"]
    assert isinstance(dev, dict)
    cards = dev["cards"]
    assert isinstance(cards, list)
    card = cards[0]
    assert isinstance(card, dict)
    card.pop("expected_otp")

    with pytest.raises(ValidationError, match="3DS test cards must define expected_otp"):
        RuntimeSettings.model_validate(payload)


@pytest.mark.config
def test_load_runtime_settings_uses_environment_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = tmp_path / "paynkolay-settings.json"
    config_file.write_text(json.dumps(valid_settings_payload()), encoding="utf-8")

    monkeypatch.setenv("PAYNKOLAY_CONFIG_FILE", str(config_file))
    monkeypatch.setenv("PAYNKOLAY_ENV", "uat")

    settings = load_runtime_settings()

    assert settings.current.name is EnvironmentName.UAT
    assert settings.current.merchant.merchant_id == "merchant-uat"


@pytest.mark.config
def test_example_runtime_settings_template_matches_schema() -> None:
    template_path = (
        Path(__file__).parents[2] / "examples" / "config" / "paynkolay-settings.example.json"
    )

    settings = RuntimeSettings.model_validate_json(template_path.read_text(encoding="utf-8"))

    assert settings.current.name is EnvironmentName.DEV
    assert settings.current.merchant.cancel_refund_api_key is not None
    assert settings.current.cards[0].alias == "synthetic_3ds_success"
