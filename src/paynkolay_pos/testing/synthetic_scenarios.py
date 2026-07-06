"""Synthetic scenario catalogue generation for local scale testing."""

from __future__ import annotations

import json
from enum import StrEnum

from paynkolay_pos.models import PaymentChannel, PaymentStatus
from paynkolay_pos.scenarios import PaymentScenarioCatalog


class SyntheticScenarioProfile(StrEnum):
    """Scenario mix profiles for generated private catalogues."""

    MIXED = "mixed"
    THREE_DS = "three_ds"
    MOTO = "moto"
    NEGATIVE = "negative"


def generate_synthetic_scenario_payloads(
    count: int,
    *,
    scenario_prefix: str = "synthetic_scenario",
    card_alias_prefix: str = "synthetic_card",
    profile: SyntheticScenarioProfile | str = SyntheticScenarioProfile.MIXED,
    card_count: int | None = None,
) -> list[dict[str, object]]:
    """Generate schema-valid synthetic payment scenario dictionaries."""

    if count < 1:
        raise ValueError("count must be greater than zero")
    if card_count is not None and card_count < 1:
        raise ValueError("card_count must be greater than zero when supplied")
    if not scenario_prefix.strip():
        raise ValueError("scenario_prefix must not be empty")
    if not card_alias_prefix.strip():
        raise ValueError("card_alias_prefix must not be empty")

    normalized_profile = SyntheticScenarioProfile(profile)
    effective_card_count = card_count or count
    scenarios: list[dict[str, object]] = []
    for index in range(count):
        kind = _scenario_kind(index, normalized_profile)
        scenario_number = index + 1
        scenarios.append(
            _scenario_payload(
                index=index,
                scenario_id=f"{scenario_prefix}_{scenario_number:04d}_{kind}",
                card_alias=f"{card_alias_prefix}_{(index % effective_card_count) + 1:04d}",
                kind=kind,
            )
        )

    return scenarios


def generate_synthetic_scenario_catalog_payload(
    count: int,
    *,
    scenario_prefix: str = "synthetic_scenario",
    card_alias_prefix: str = "synthetic_card",
    profile: SyntheticScenarioProfile | str = SyntheticScenarioProfile.MIXED,
    card_count: int | None = None,
) -> dict[str, object]:
    """Generate a complete payment scenario catalogue payload."""

    return {
        "scenarios": generate_synthetic_scenario_payloads(
            count,
            scenario_prefix=scenario_prefix,
            card_alias_prefix=card_alias_prefix,
            profile=profile,
            card_count=card_count,
        )
    }


def generate_synthetic_scenario_catalog_json(
    count: int,
    *,
    scenario_prefix: str = "synthetic_scenario",
    card_alias_prefix: str = "synthetic_card",
    profile: SyntheticScenarioProfile | str = SyntheticScenarioProfile.MIXED,
    card_count: int | None = None,
) -> str:
    """Generate pretty JSON for a synthetic payment scenario catalogue."""

    catalog = generate_synthetic_scenario_catalog_payload(
        count,
        scenario_prefix=scenario_prefix,
        card_alias_prefix=card_alias_prefix,
        profile=profile,
        card_count=card_count,
    )
    return json.dumps(catalog, indent=2, ensure_ascii=False)


def validate_synthetic_scenario_catalog(
    payload: dict[str, object],
) -> PaymentScenarioCatalog:
    """Validate generated scenario dictionaries against the scenario model."""

    return PaymentScenarioCatalog.model_validate(payload)


def _scenario_payload(
    *,
    index: int,
    scenario_id: str,
    card_alias: str,
    kind: str,
) -> dict[str, object]:
    amount = f"{((index % 50) + 1) * 10}.00"
    if kind == "moto":
        return {
            "scenario_id": scenario_id,
            "title": f"Synthetic MoTo authorized payment {index + 1}",
            "card_alias": card_alias,
            "amount": amount,
            "currency": "TRY",
            "requires_3ds": False,
            "expected_initialize_status": PaymentStatus.AUTHORIZED.value,
            "expected_final_status": PaymentStatus.AUTHORIZED.value,
            "installment_count": 1,
            "payment_channel": PaymentChannel.MOTO.value,
            "moto": True,
            "tags": ["synthetic", "moto"],
        }
    if kind == "declined":
        return {
            "scenario_id": scenario_id,
            "title": f"Synthetic declined 3DS payment {index + 1}",
            "card_alias": card_alias,
            "amount": amount,
            "currency": "TRY",
            "requires_3ds": True,
            "expected_initialize_status": PaymentStatus.PENDING_3DS.value,
            "expected_final_status": PaymentStatus.FAILED.value,
            "installment_count": 1,
            "payment_channel": PaymentChannel.E_COMMERCE.value,
            "moto": False,
            "tags": ["synthetic", "negative", "three_ds"],
        }
    if kind == "installment":
        return {
            "scenario_id": scenario_id,
            "title": f"Synthetic installment 3DS payment {index + 1}",
            "card_alias": card_alias,
            "amount": amount,
            "currency": "TRY",
            "requires_3ds": True,
            "expected_initialize_status": PaymentStatus.PENDING_3DS.value,
            "expected_final_status": PaymentStatus.CAPTURED.value,
            "installment_count": (index % 12) + 1,
            "payment_channel": PaymentChannel.E_COMMERCE.value,
            "moto": False,
            "tags": ["synthetic", "installment", "three_ds"],
        }
    return {
        "scenario_id": scenario_id,
        "title": f"Synthetic 3DS captured payment {index + 1}",
        "card_alias": card_alias,
        "amount": amount,
        "currency": "TRY",
        "requires_3ds": True,
        "expected_initialize_status": PaymentStatus.PENDING_3DS.value,
        "expected_final_status": PaymentStatus.CAPTURED.value,
        "installment_count": 1,
        "payment_channel": PaymentChannel.E_COMMERCE.value,
        "moto": False,
        "tags": ["synthetic", "three_ds"],
    }


def _scenario_kind(index: int, profile: SyntheticScenarioProfile) -> str:
    if profile is SyntheticScenarioProfile.THREE_DS:
        return "three_ds"
    if profile is SyntheticScenarioProfile.MOTO:
        return "moto"
    if profile is SyntheticScenarioProfile.NEGATIVE:
        return "declined"
    return ("three_ds", "installment", "declined", "moto")[index % 4]
