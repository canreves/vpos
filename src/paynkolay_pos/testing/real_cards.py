"""Read real test cards from provider CSV files into schema-valid card payloads.

Paynkolay and Param provide their sandbox test cards as CSV exports with
different column layouts and date formats. This module normalizes both into the
runtime ``TestCard`` shape. For the first pass all real cards are read as MoTo
(requires_3ds=False) so no OTP is required; 3DS handling is deferred until
sandbox OTP behavior is confirmed.
"""

from __future__ import annotations

import csv
from pathlib import Path

from paynkolay_pos.config import CardBrand

_BRAND_ALIASES = {
    "visa": CardBrand.VISA,
    "mastercard": CardBrand.MASTERCARD,
    "master": CardBrand.MASTERCARD,
    "troy": CardBrand.TROY,
}


def _normalize_brand(raw: str) -> str:
    text = raw.strip().lower()
    for key, brand in _BRAND_ALIASES.items():
        if key in text:
            return brand.value
    raise ValueError(f"unrecognized card brand: {raw!r}")


def _two_digit_year_to_full(year: str) -> int:
    value = int(year)
    return 2000 + value if value < 100 else value


def read_paynkolay_cards(path: str | Path) -> list[dict[str, object]]:
    """Read Paynkolay CSV (date format YYYY/MM) into MoTo card payloads."""

    cards: list[dict[str, object]] = []
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for index, row in enumerate(csv.DictReader(handle), start=1):
            year_str, month_str = row["Son Kullanma Tarihi"].strip().split("/")
            cards.append(
                {
                    "alias": f"paynkolay_real_{index:04d}",
                    "brand": _normalize_brand(row["Kart Semasi"]),
                    "pan": row["Kart Numarasi"].strip(),
                    "expiry_month": int(month_str),
                    "expiry_year": _two_digit_year_to_full(year_str),
                    "cvv": row["CVC Kodu"].strip(),
                    "requires_3ds": False,
                }
            )
    return cards


def read_param_cards(path: str | Path) -> list[dict[str, object]]:
    """Read Param CSV (date format MM/YY, brand inside 'Kart Tipi') into MoTo payloads."""

    cards: list[dict[str, object]] = []
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for index, row in enumerate(csv.DictReader(handle), start=1):
            month_str, year_str = row["Son Kullanma Tarihi"].strip().split("/")
            cards.append(
                {
                    "alias": f"param_real_{index:04d}",
                    "brand": _normalize_brand(row["Kart Tipi"]),
                    "pan": row["Kart Numarasi"].strip(),
                    "expiry_month": int(month_str),
                    "expiry_year": _two_digit_year_to_full(year_str),
                    "cvv": row["Guvenlik Numarasi (CVV)"].strip(),
                    "requires_3ds": False,
                }
            )
    return cards


def build_combined_card_dataset(
    *,
    paynkolay_csv: str | Path,
    param_csv: str | Path,
    total_count: int = 100,
) -> list[dict[str, object]]:
    """Combine real provider cards with synthetic MoTo fillers up to total_count.

    Real cards (Paynkolay + Param) are placed first and preserved as-is. The
    remainder is topped up with synthetic MoTo cards so the dataset reaches
    total_count. All aliases are guaranteed unique.
    """

    from paynkolay_pos.testing.synthetic_cards import (
        SyntheticCardProfile,
        generate_synthetic_card_payloads,
    )

    real_cards = read_paynkolay_cards(paynkolay_csv) + read_param_cards(param_csv)
    real_count = len(real_cards)

    if total_count < real_count:
        raise ValueError(
            f"total_count ({total_count}) is smaller than the number of real "
            f"cards ({real_count})"
        )

    filler_count = total_count - real_count
    filler_cards = generate_synthetic_card_payloads(
        filler_count,
        alias_prefix="synthetic_filler",
        profile=SyntheticCardProfile.MOTO,
    ) if filler_count > 0 else []

    combined = real_cards + filler_cards

    aliases = [card["alias"] for card in combined]
    if len(aliases) != len(set(aliases)):
        raise ValueError("combined dataset contains duplicate aliases")

    return combined

