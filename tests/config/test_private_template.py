from __future__ import annotations

import json
from pathlib import Path

import pytest

from paynkolay_pos.config import (
    REQUIRED_SANDBOX_CARDS,
    RuntimeSettings,
    build_private_runtime_config_json,
    build_private_runtime_config_payload,
)
from paynkolay_pos.scenarios import load_payment_scenario_catalog


@pytest.mark.config
def test_private_runtime_config_payload_builds_100_cards_per_environment() -> None:
    payload = build_private_runtime_config_payload(card_count=100)
    settings = RuntimeSettings.model_validate(payload)

    assert settings.active_environment == "dev"
    for environment in settings.environments.values():
        assert len(environment.cards) == 100


@pytest.mark.config
def test_private_runtime_config_keeps_checked_in_scenario_aliases() -> None:
    payload = build_private_runtime_config_payload(card_count=100)
    settings = RuntimeSettings.model_validate(payload)
    catalog = load_payment_scenario_catalog(
        Path(__file__).parents[2] / "examples" / "scenarios" / "payment_scenarios.json"
    )

    configured_aliases = {card.alias for card in settings.current.cards}
    scenario_aliases = {scenario.card_alias for scenario in catalog.scenarios}

    assert scenario_aliases <= configured_aliases


@pytest.mark.config
def test_private_runtime_config_starts_with_required_sandbox_cards() -> None:
    payload = build_private_runtime_config_payload(card_count=100)
    settings = RuntimeSettings.model_validate(payload)

    aliases = [card.alias for card in settings.current.cards[: len(REQUIRED_SANDBOX_CARDS)]]

    assert aliases == [str(card["alias"]) for card in REQUIRED_SANDBOX_CARDS]


@pytest.mark.config
def test_private_runtime_config_json_serializes_valid_settings() -> None:
    body = build_private_runtime_config_json(card_count=12, profile="moto")
    payload = json.loads(body)
    settings = RuntimeSettings.model_validate(payload)

    filler_cards = settings.current.cards[len(REQUIRED_SANDBOX_CARDS) :]

    assert len(settings.current.cards) == 12
    assert all(not card.requires_3ds for card in filler_cards)


@pytest.mark.config
def test_private_runtime_config_rejects_too_few_cards() -> None:
    with pytest.raises(ValueError, match="card_count must be at least"):
        build_private_runtime_config_payload(card_count=len(REQUIRED_SANDBOX_CARDS) - 1)
