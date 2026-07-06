from __future__ import annotations

import json

import pytest

from paynkolay_pos.config import RuntimeSettings
from paynkolay_pos.testing import (
    SyntheticCardProfile,
    generate_synthetic_card_payloads,
    generate_synthetic_cards_json,
    validate_synthetic_card_payloads,
)


def test_generate_synthetic_card_payloads_builds_unique_schema_valid_cards() -> None:
    cards = generate_synthetic_card_payloads(100)

    aliases = {str(card["alias"]) for card in cards}
    validated_cards = validate_synthetic_card_payloads(cards)

    assert len(cards) == 100
    assert len(aliases) == 100
    assert len(validated_cards) == 100
    assert cards[0]["alias"] == "synthetic_card_0001"
    assert cards[0]["requires_3ds"] is True
    assert cards[0]["expected_otp"] == "000000"
    assert cards[1]["requires_3ds"] is False
    assert "expected_otp" not in cards[1]


@pytest.mark.parametrize(
    ("profile", "expected_requires_3ds"),
    [
        (SyntheticCardProfile.THREE_DS, True),
        (SyntheticCardProfile.MOTO, False),
    ],
)
def test_generate_synthetic_card_payloads_supports_profiles(
    profile: SyntheticCardProfile,
    expected_requires_3ds: bool,
) -> None:
    cards = generate_synthetic_card_payloads(5, profile=profile)

    assert all(card["requires_3ds"] is expected_requires_3ds for card in cards)
    validate_synthetic_card_payloads(cards)


def test_generate_synthetic_cards_json_serializes_card_array() -> None:
    body = generate_synthetic_cards_json(2, alias_prefix="private_card")

    cards = json.loads(body)

    assert isinstance(cards, list)
    assert cards[0]["alias"] == "private_card_0001"
    assert cards[1]["alias"] == "private_card_0002"


@pytest.mark.config
def test_generated_synthetic_cards_validate_in_runtime_settings() -> None:
    settings = RuntimeSettings.model_validate(
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
                    "cards": generate_synthetic_card_payloads(100),
                }
            },
        }
    )

    assert len(settings.current.cards) == 100


def test_generate_synthetic_card_payloads_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="count must be greater than zero"):
        generate_synthetic_card_payloads(0)

    with pytest.raises(ValueError, match="alias_prefix must not be empty"):
        generate_synthetic_card_payloads(1, alias_prefix=" ")
