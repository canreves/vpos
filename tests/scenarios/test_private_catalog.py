from __future__ import annotations

import json

import pytest

from paynkolay_pos.config import RuntimeSettings, build_private_runtime_config_payload
from paynkolay_pos.sandbox import check_sandbox_readiness
from paynkolay_pos.scenarios import (
    PaymentScenarioCatalog,
    build_private_scenario_catalog_json,
    build_private_scenario_catalog_payload,
)


@pytest.mark.scenario
def test_private_scenario_catalog_uses_every_generated_config_card_alias() -> None:
    settings = RuntimeSettings.model_validate(build_private_runtime_config_payload(card_count=100))
    catalog = PaymentScenarioCatalog.model_validate(
        build_private_scenario_catalog_payload(card_count=100)
    )

    configured_aliases = {card.alias for card in settings.current.cards}
    scenario_aliases = {scenario.card_alias for scenario in catalog.scenarios}

    assert configured_aliases <= scenario_aliases
    assert all("sandbox" in scenario.tags for scenario in catalog.scenarios)


@pytest.mark.scenario
def test_private_scenario_catalog_readiness_only_reports_placeholders() -> None:
    settings = RuntimeSettings.model_validate(build_private_runtime_config_payload(card_count=100))
    catalog = PaymentScenarioCatalog.model_validate(
        build_private_scenario_catalog_payload(card_count=100)
    )

    report = check_sandbox_readiness(settings, catalog)

    assert {issue.code for issue in report.issues} == {"placeholder_value"}


@pytest.mark.scenario
def test_private_scenario_catalog_targets_selected_environment_aliases() -> None:
    payload = build_private_scenario_catalog_payload(card_count=12, environment="uat")
    catalog = PaymentScenarioCatalog.model_validate(payload)
    aliases = {scenario.card_alias for scenario in catalog.scenarios}

    assert "synthetic_env2_card_0001" in aliases
    assert "synthetic_env1_card_0001" not in aliases


@pytest.mark.scenario
def test_private_scenario_catalog_json_serializes_valid_catalogue() -> None:
    body = build_private_scenario_catalog_json(card_count=12, profile="moto")
    payload = json.loads(body)
    catalog = PaymentScenarioCatalog.model_validate(payload)

    synthetic_scenarios = [
        scenario for scenario in catalog.scenarios if "synthetic" in scenario.tags
    ]

    assert synthetic_scenarios
    assert all(scenario.moto for scenario in synthetic_scenarios)


@pytest.mark.scenario
def test_private_scenario_catalog_rejects_unknown_environment() -> None:
    with pytest.raises(ValueError, match="environment must be one of"):
        build_private_scenario_catalog_payload(environment="prod")
