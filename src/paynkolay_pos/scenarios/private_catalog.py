"""Private sandbox scenario catalogue builder."""

from __future__ import annotations

import json

from paynkolay_pos.config.private_template import build_private_runtime_config_payload
from paynkolay_pos.scenarios.payments import (
    DEFAULT_PAYMENT_SCENARIO_CATALOG_PATH,
    PaymentScenarioCatalog,
    load_payment_scenario_catalog,
)

_ENVIRONMENT_INDEX = {"dev": 0, "uat": 1, "test": 2}


def build_private_scenario_catalog_payload(
    *,
    card_count: int = 100,
    environment: str = "dev",
    profile: str = "mixed",
) -> dict[str, object]:
    """Build a sandbox-tagged scenario catalogue aligned to private config aliases."""

    environment_name = _normalize_environment(environment)
    settings_payload = build_private_runtime_config_payload(card_count=card_count, profile=profile)
    environments = settings_payload["environments"]
    if not isinstance(environments, dict):
        raise TypeError("generated settings payload did not include environments")

    environment_payload = environments[environment_name]
    if not isinstance(environment_payload, dict):
        raise TypeError("generated environment payload is invalid")
    cards = environment_payload["cards"]
    if not isinstance(cards, list):
        raise TypeError("generated environment payload did not include cards")

    base_scenarios = _sandbox_base_scenarios()
    used_aliases = {str(scenario["card_alias"]) for scenario in base_scenarios}
    filler_scenarios = [
        _filler_scenario(card, index=index, environment=environment_name)
        for index, card in enumerate(cards, start=1)
        if isinstance(card, dict) and str(card["alias"]) not in used_aliases
    ]

    payload: dict[str, object] = {"scenarios": base_scenarios + filler_scenarios}
    PaymentScenarioCatalog.model_validate(payload)
    return payload


def build_private_scenario_catalog_json(
    *,
    card_count: int = 100,
    environment: str = "dev",
    profile: str = "mixed",
) -> str:
    """Build pretty JSON for a private sandbox scenario catalogue."""

    payload = build_private_scenario_catalog_payload(
        card_count=card_count,
        environment=environment,
        profile=profile,
    )
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _sandbox_base_scenarios() -> list[dict[str, object]]:
    catalog = load_payment_scenario_catalog(DEFAULT_PAYMENT_SCENARIO_CATALOG_PATH)
    scenarios: list[dict[str, object]] = []
    for scenario in catalog.scenarios:
        payload = scenario.model_dump(mode="json")
        payload["tags"] = _with_sandbox_tag(payload["tags"])
        scenarios.append(payload)
    return scenarios


def _with_sandbox_tag(tags: object) -> list[str]:
    if not isinstance(tags, list):
        raise TypeError("scenario tags must serialize to a list")
    return tags if "sandbox" in tags else ["sandbox", *tags]


def _filler_scenario(
    card: dict[str, object],
    *,
    index: int,
    environment: str,
) -> dict[str, object]:
    alias = str(card["alias"])
    requires_3ds = bool(card["requires_3ds"])
    scenario_id = f"{environment}_{alias}_smoke"
    if requires_3ds:
        return {
            "scenario_id": scenario_id,
            "title": f"{environment.upper()} {alias} 3DS smoke payment",
            "card_alias": alias,
            "amount": "10.00",
            "currency": "TRY",
            "requires_3ds": True,
            "expected_initialize_status": "pending_3ds",
            "expected_final_status": "captured",
            "installment_count": 1,
            "payment_channel": "e_commerce",
            "moto": False,
            "tags": ["sandbox", "synthetic", "three_ds"],
        }
    return {
        "scenario_id": scenario_id,
        "title": f"{environment.upper()} {alias} MoTo smoke payment",
        "card_alias": alias,
        "amount": "10.00",
        "currency": "TRY",
        "requires_3ds": False,
        "expected_initialize_status": "authorized",
        "expected_final_status": "authorized",
        "installment_count": 1,
        "payment_channel": "moto",
        "moto": True,
        "tags": ["sandbox", "synthetic", "moto"],
    }


def _normalize_environment(environment: str) -> str:
    normalized = environment.strip().lower()
    if normalized not in _ENVIRONMENT_INDEX:
        raise ValueError("environment must be one of: dev, uat, test")
    return normalized
