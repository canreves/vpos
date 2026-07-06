from __future__ import annotations

import json

import pytest

from paynkolay_pos.models import PaymentChannel, PaymentStatus
from paynkolay_pos.testing import (
    SyntheticScenarioProfile,
    generate_synthetic_scenario_catalog_json,
    generate_synthetic_scenario_catalog_payload,
    generate_synthetic_scenario_payloads,
    validate_synthetic_scenario_catalog,
)


def test_generate_synthetic_scenario_payloads_builds_valid_mixed_catalogue() -> None:
    payload = generate_synthetic_scenario_catalog_payload(
        1000,
        card_count=100,
    )

    catalog = validate_synthetic_scenario_catalog(payload)
    scenario_ids = catalog.ids()
    card_aliases = {scenario.card_alias for scenario in catalog.scenarios}

    assert len(catalog.scenarios) == 1000
    assert len(set(scenario_ids)) == 1000
    assert len(card_aliases) == 100
    assert catalog.scenarios[0].expected_final_status is PaymentStatus.CAPTURED
    assert catalog.scenarios[1].installment_count == 2
    assert catalog.scenarios[2].expected_final_status is PaymentStatus.FAILED
    assert catalog.scenarios[3].payment_channel is PaymentChannel.MOTO


@pytest.mark.parametrize(
    ("profile", "expected_tag"),
    [
        (SyntheticScenarioProfile.THREE_DS, "three_ds"),
        (SyntheticScenarioProfile.MOTO, "moto"),
        (SyntheticScenarioProfile.NEGATIVE, "negative"),
    ],
)
def test_generate_synthetic_scenario_payloads_supports_profiles(
    profile: SyntheticScenarioProfile,
    expected_tag: str,
) -> None:
    scenarios = generate_synthetic_scenario_payloads(10, profile=profile)
    catalog = validate_synthetic_scenario_catalog({"scenarios": scenarios})

    assert all(expected_tag in scenario.tags for scenario in catalog.scenarios)


def test_generate_synthetic_scenario_catalog_json_serializes_catalogue() -> None:
    body = generate_synthetic_scenario_catalog_json(
        2,
        scenario_prefix="private_scenario",
        card_alias_prefix="private_card",
    )

    payload = json.loads(body)
    catalog = validate_synthetic_scenario_catalog(payload)

    assert catalog.ids() == (
        "private_scenario_0001_three_ds",
        "private_scenario_0002_installment",
    )
    assert catalog.scenarios[0].card_alias == "private_card_0001"
    assert catalog.scenarios[1].card_alias == "private_card_0002"


def test_generate_synthetic_scenario_payloads_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="count must be greater than zero"):
        generate_synthetic_scenario_payloads(0)

    with pytest.raises(ValueError, match="card_count must be greater than zero"):
        generate_synthetic_scenario_payloads(1, card_count=0)

    with pytest.raises(ValueError, match="scenario_prefix must not be empty"):
        generate_synthetic_scenario_payloads(1, scenario_prefix=" ")

    with pytest.raises(ValueError, match="card_alias_prefix must not be empty"):
        generate_synthetic_scenario_payloads(1, card_alias_prefix=" ")
