"""Synthetic card dataset generation for local scale testing."""

from __future__ import annotations

import json
from enum import StrEnum

from paynkolay_pos.config import CardBrand, TestCard


class SyntheticCardProfile(StrEnum):
    """Card mix profiles for generated private test datasets."""

    MIXED = "mixed"
    THREE_DS = "three_ds"
    MOTO = "moto"


def generate_synthetic_card_payloads(
    count: int,
    *,
    alias_prefix: str = "synthetic_card",
    profile: SyntheticCardProfile | str = SyntheticCardProfile.MIXED,
) -> list[dict[str, object]]:
    """Generate schema-valid synthetic card dictionaries for private config files."""

    if count < 1:
        raise ValueError("count must be greater than zero")
    if not alias_prefix.strip():
        raise ValueError("alias_prefix must not be empty")

    normalized_profile = SyntheticCardProfile(profile)
    cards: list[dict[str, object]] = []
    for index in range(count):
        requires_3ds = _requires_3ds(index, normalized_profile)
        card: dict[str, object] = {
            "alias": f"{alias_prefix}_{index + 1:04d}",
            "brand": _brand(index).value,
            "pan": f"{index:016d}",
            "expiry_month": (index % 12) + 1,
            "expiry_year": 2030 + (index % 5),
            "cvv": f"{index % 1000:03d}",
            "requires_3ds": requires_3ds,
        }
        if requires_3ds:
            card["expected_otp"] = f"{index % 1000000:06d}"
        cards.append(card)

    return cards


def generate_synthetic_cards_json(
    count: int,
    *,
    alias_prefix: str = "synthetic_card",
    profile: SyntheticCardProfile | str = SyntheticCardProfile.MIXED,
) -> str:
    """Generate pretty JSON for a synthetic ``cards`` array."""

    cards = generate_synthetic_card_payloads(
        count,
        alias_prefix=alias_prefix,
        profile=profile,
    )
    return json.dumps(cards, indent=2, ensure_ascii=False)


def validate_synthetic_card_payloads(cards: list[dict[str, object]]) -> tuple[TestCard, ...]:
    """Validate generated card dictionaries against the runtime config model."""

    return tuple(TestCard.model_validate(card) for card in cards)


def _requires_3ds(index: int, profile: SyntheticCardProfile) -> bool:
    if profile is SyntheticCardProfile.THREE_DS:
        return True
    if profile is SyntheticCardProfile.MOTO:
        return False
    return index % 2 == 0


def _brand(index: int) -> CardBrand:
    brands = (CardBrand.VISA, CardBrand.MASTERCARD, CardBrand.TROY)
    return brands[index % len(brands)]
