"""Build local/mock test matrices from externally supplied credential CSV files."""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class CredentialCardMatrixItem:
    """One normalized card row for local/mock scenario planning."""

    alias: str
    source: str
    bank_name: str
    brand: str
    card_type: str
    pan: str
    expiry_month: int
    expiry_year: int
    cvv: str
    requires_3ds: bool
    expected_otp: str | None
    recommended_scenarios: tuple[str, ...]


@dataclass(frozen=True)
class CredentialErrorMatrixItem:
    """One normalized error row for local/mock negative scenario planning."""

    scenario_id: str
    cvv: str
    expected_error_code: str
    expected_error_message: str
    input_condition: str


def build_credential_matrix_payload(
    *,
    param_cards_path: Path | None = None,
    paynkolay_cards_path: Path | None = None,
    error_codes_path: Path | None = None,
) -> dict[str, object]:
    """Build a normalized matrix payload from available local credential files."""

    cards: list[CredentialCardMatrixItem] = []
    if param_cards_path is not None and param_cards_path.is_file():
        cards.extend(_read_param_cards(param_cards_path))
    if paynkolay_cards_path is not None and paynkolay_cards_path.is_file():
        cards.extend(_read_paynkolay_cards(paynkolay_cards_path))

    errors: list[CredentialErrorMatrixItem] = []
    if error_codes_path is not None and error_codes_path.is_file():
        errors.extend(_read_error_codes(error_codes_path))

    return {
        "summary": {
            "card_count": len(cards),
            "three_ds_card_count": sum(1 for card in cards if card.requires_3ds),
            "moto_candidate_count": sum(1 for card in cards if not card.requires_3ds),
            "error_case_count": len(errors),
            "brands": sorted({card.brand for card in cards}),
            "card_types": sorted({card.card_type for card in cards}),
        },
        "cards": [asdict(card) for card in cards],
        "errors": [asdict(error) for error in errors],
    }


def build_credential_matrix_json(
    *,
    param_cards_path: Path | None = None,
    paynkolay_cards_path: Path | None = None,
    error_codes_path: Path | None = None,
) -> str:
    """Build pretty JSON for the local/mock credential matrix."""

    payload = build_credential_matrix_payload(
        param_cards_path=param_cards_path,
        paynkolay_cards_path=paynkolay_cards_path,
        error_codes_path=error_codes_path,
    )
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _read_param_cards(path: Path) -> list[CredentialCardMatrixItem]:
    rows = _read_csv(path)
    cards: list[CredentialCardMatrixItem] = []
    for index, row in enumerate(rows, start=1):
        card_type_text = _value(row, "Kart Tipi")
        pan = _digits(_value(row, "Kart Numarasi"))
        month, year = _parse_expiry(_value(row, "Son Kullanma Tarihi"))
        otp = _extract_otp(card_type_text)
        requires_3ds = bool(otp) or "3ds" in card_type_text.lower()
        cards.append(
            _card_item(
                source=path.name,
                index=index,
                bank_name=_value(row, "Banka"),
                brand=_infer_brand(card_type_text),
                card_type=_infer_card_type(card_type_text),
                pan=pan,
                expiry_month=month,
                expiry_year=year,
                cvv=_digits(_value(row, "Guvenlik Numarasi (CVV)")),
                requires_3ds=requires_3ds,
                expected_otp=otp,
            )
        )
    return cards


def _read_paynkolay_cards(path: Path) -> list[CredentialCardMatrixItem]:
    rows = _read_csv(path)
    cards: list[CredentialCardMatrixItem] = []
    for index, row in enumerate(rows, start=1):
        pan = _digits(_value(row, "Kart Numarasi"))
        month, year = _parse_expiry(_value(row, "Son Kullanma Tarihi"))
        otp = _digits(_value(row, "Sifre")) or None
        cards.append(
            _card_item(
                source=path.name,
                index=index,
                bank_name=_value(row, "Banka Adi"),
                brand=_infer_brand(_value(row, "Kart Semasi")),
                card_type="credit",
                pan=pan,
                expiry_month=month,
                expiry_year=year,
                cvv=_digits(_value(row, "CVC Kodu")),
                requires_3ds=otp is not None,
                expected_otp=otp,
            )
        )
    return cards


def _read_error_codes(path: Path) -> list[CredentialErrorMatrixItem]:
    rows = _read_csv(path)
    errors: list[CredentialErrorMatrixItem] = []
    for row in rows:
        cvv = _digits(_value(row, "CVV"))
        code = _value(row, "Hata Kodu")
        message = _value(row, "Hata Aciklamasi")
        errors.append(
            CredentialErrorMatrixItem(
                scenario_id=f"cvv_{cvv}_error_{code}",
                cvv=cvv,
                expected_error_code=code,
                expected_error_message=message,
                input_condition=f"Use CVV {cvv} to trigger provider error {code}.",
            )
        )
    return errors


def _card_item(
    *,
    source: str,
    index: int,
    bank_name: str,
    brand: str,
    card_type: str,
    pan: str,
    expiry_month: int,
    expiry_year: int,
    cvv: str,
    requires_3ds: bool,
    expected_otp: str | None,
) -> CredentialCardMatrixItem:
    alias = f"{_slug(bank_name)}_{brand}_{pan[-4:] or index:0>4}"
    return CredentialCardMatrixItem(
        alias=alias,
        source=source,
        bank_name=bank_name,
        brand=brand,
        card_type=card_type,
        pan=pan,
        expiry_month=expiry_month,
        expiry_year=expiry_year,
        cvv=cvv,
        requires_3ds=requires_3ds,
        expected_otp=expected_otp,
        recommended_scenarios=_recommended_scenarios(
            card_type=card_type,
            requires_3ds=requires_3ds,
        ),
    )


def _recommended_scenarios(*, card_type: str, requires_3ds: bool) -> tuple[str, ...]:
    scenarios = ["three_ds_success"] if requires_3ds else ["moto_authorized"]
    scenarios.append("debit_coverage" if card_type == "debit" else "credit_coverage")
    if card_type == "credit":
        scenarios.append("installment_candidate")
    return tuple(scenarios)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _value(row: dict[str, str], key: str) -> str:
    return (row.get(key) or "").strip()


def _digits(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def _parse_expiry(value: str) -> tuple[int, int]:
    parts = _digits(value)
    if len(parts) == 4:
        month = int(parts[:2])
        year = int(parts[2:])
        return month, 2000 + year
    if len(parts) == 6:
        year = int(parts[:4])
        month = int(parts[4:])
        return month, year
    raise ValueError(f"unsupported expiry format: {value!r}")


def _infer_brand(value: str) -> str:
    normalized = value.lower()
    if "master" in normalized:
        return "mastercard"
    if "troy" in normalized:
        return "troy"
    return "visa"


def _infer_card_type(value: str) -> str:
    return "debit" if "debit" in value.lower() else "credit"


def _extract_otp(value: str) -> str | None:
    match = re.search(r"orn:\s*(\d{4,8})|örn:\s*(\d{4,8})", value.lower())
    if match is None:
        return None
    return next(group for group in match.groups() if group)


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_value).strip("_")
    return slug or "card"
