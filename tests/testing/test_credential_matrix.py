from __future__ import annotations

import json
from pathlib import Path

import pytest

from paynkolay_pos.config import RuntimeSettings
from paynkolay_pos.scenarios import PaymentScenarioCatalog
from paynkolay_pos.testing import (
    build_credential_matrix_json,
    build_credential_matrix_payload,
    build_credential_runtime_config_json,
    build_credential_runtime_config_payload,
    build_credential_scenario_catalog_json,
    build_credential_scenario_catalog_payload,
)


def test_build_credential_matrix_payload_normalizes_cards_and_errors(tmp_path: Path) -> None:
    param_cards = tmp_path / "param_merchants.csv"
    param_cards.write_text(
        "\ufeffBanka,Kart Numarasi,Son Kullanma Tarihi,Guvenlik Numarasi (CVV),"
        "Ticari Kart,Kart Tipi\n"
        "Is Bankasi,6501738564461396,12/26,000,Hayir,"
        "Kredi Karti / TROY - 3DS Sifre: test (orn: 102824)\n"
        "Halk Bankasi,5818775818772285,12/26,001,Hayir,Debit / MASTERCARD\n",
        encoding="utf-8",
    )
    paynkolay_cards = tmp_path / "paynkolay_merchants.csv"
    paynkolay_cards.write_text(
        "\ufeffBanka Adi,Kart Numarasi,Kart Semasi,Son Kullanma Tarihi,CVC Kodu,Sifre\n"
        "DenizBank,5200190006338608,MasterCard,2030/01,410,123456\n",
        encoding="utf-8",
    )
    errors = tmp_path / "param_hata_kodlari.csv"
    errors.write_text(
        "\ufeffCVV,Hata Kodu,Hata Aciklamasi\n"
        "510,51,Limit Yetersiz\n",
        encoding="utf-8",
    )

    payload = build_credential_matrix_payload(
        param_cards_path=param_cards,
        paynkolay_cards_path=paynkolay_cards,
        error_codes_path=errors,
    )

    assert payload["summary"] == {
        "card_count": 3,
        "three_ds_card_count": 2,
        "moto_candidate_count": 1,
        "error_case_count": 1,
        "brands": ["mastercard", "troy"],
        "card_types": ["credit", "debit"],
    }
    cards = payload["cards"]
    assert isinstance(cards, list)
    assert cards[0]["brand"] == "troy"
    assert cards[0]["requires_3ds"] is True
    assert cards[0]["expected_otp"] == "102824"
    assert cards[1]["card_type"] == "debit"
    assert cards[1]["recommended_scenarios"] == ("moto_authorized", "debit_coverage")
    assert cards[2]["expiry_month"] == 1
    assert cards[2]["expiry_year"] == 2030

    error_items = payload["errors"]
    assert isinstance(error_items, list)
    assert error_items[0]["scenario_id"] == "cvv_510_error_51"
    assert error_items[0]["expected_error_message"] == "Limit Yetersiz"


def test_build_credential_matrix_json_serializes_payload(tmp_path: Path) -> None:
    errors = tmp_path / "param_hata_kodlari.csv"
    errors.write_text(
        "\ufeffCVV,Hata Kodu,Hata Aciklamasi\n"
        "120,12,Gecersiz Islem\n",
        encoding="utf-8",
    )

    body = build_credential_matrix_json(error_codes_path=errors)
    payload = json.loads(body)

    assert payload["summary"]["card_count"] == 0
    assert payload["summary"]["error_case_count"] == 1
    assert payload["errors"][0]["input_condition"] == (
        "Use CVV 120 to trigger provider error 12."
    )


def test_build_credential_scenario_catalog_payload_validates(tmp_path: Path) -> None:
    param_cards = tmp_path / "param_merchants.csv"
    param_cards.write_text(
        "\ufeffBanka,Kart Numarasi,Son Kullanma Tarihi,Guvenlik Numarasi (CVV),"
        "Ticari Kart,Kart Tipi\n"
        "Is Bankasi,6501738564461396,12/26,000,Hayir,"
        "Kredi Karti / TROY - 3DS Sifre: test (orn: 102824)\n"
        "Halk Bankasi,5818775818772285,12/26,001,Hayir,Debit / MASTERCARD\n",
        encoding="utf-8",
    )
    errors = tmp_path / "param_hata_kodlari.csv"
    errors.write_text(
        "\ufeffCVV,Hata Kodu,Hata Aciklamasi\n"
        "510,51,Limit Yetersiz\n",
        encoding="utf-8",
    )

    payload = build_credential_scenario_catalog_payload(
        param_cards_path=param_cards,
        error_codes_path=errors,
    )
    catalog = PaymentScenarioCatalog.model_validate(payload)

    assert len(catalog.scenarios) == 4
    assert catalog.scenarios[0].scenario_id == "credential_is_bankasi_troy_1396_3ds_success"
    assert catalog.scenarios[0].requires_3ds is True
    assert "three_ds" in catalog.scenarios[0].tags
    assert catalog.scenarios[1].installment_count == 3
    assert catalog.scenarios[2].moto is True
    assert catalog.scenarios[3].expected_final_status.value == "failed"
    assert "invalid_cvv" in catalog.scenarios[3].tags
    assert "cvv_error" in catalog.scenarios[3].tags
    assert "error_code_51" in catalog.scenarios[3].tags


def test_build_credential_scenario_catalog_json_serializes_catalogue(tmp_path: Path) -> None:
    paynkolay_cards = tmp_path / "paynkolay_merchants.csv"
    paynkolay_cards.write_text(
        "\ufeffBanka Adi,Kart Numarasi,Kart Semasi,Son Kullanma Tarihi,CVC Kodu,Sifre\n"
        "DenizBank,5200190006338608,MasterCard,2030/01,410,123456\n",
        encoding="utf-8",
    )

    body = build_credential_scenario_catalog_json(paynkolay_cards_path=paynkolay_cards)
    payload = json.loads(body)
    catalog = PaymentScenarioCatalog.model_validate(payload)

    assert len(catalog.scenarios) == 2
    assert catalog.scenarios[0].card_alias == "denizbank_mastercard_8608"


def test_build_credential_scenario_catalog_rejects_empty_card_set() -> None:
    with pytest.raises(ValueError, match="at least one credential card"):
        build_credential_scenario_catalog_payload()


def test_build_credential_runtime_config_payload_matches_scenario_aliases(
    tmp_path: Path,
) -> None:
    param_cards = tmp_path / "param_merchants.csv"
    param_cards.write_text(
        "\ufeffBanka,Kart Numarasi,Son Kullanma Tarihi,Guvenlik Numarasi (CVV),"
        "Ticari Kart,Kart Tipi\n"
        "Is Bankasi,6501738564461396,12/26,000,Hayir,"
        "Kredi Karti / TROY - 3DS Sifre: test (orn: 102824)\n"
        "Halk Bankasi,5818775818772285,12/26,001,Hayir,Debit / MASTERCARD\n",
        encoding="utf-8",
    )

    settings = RuntimeSettings.model_validate(
        build_credential_runtime_config_payload(param_cards_path=param_cards)
    )
    catalog = PaymentScenarioCatalog.model_validate(
        build_credential_scenario_catalog_payload(param_cards_path=param_cards)
    )

    configured_aliases = {card.alias for card in settings.current.cards}
    scenario_aliases = {scenario.card_alias for scenario in catalog.scenarios}

    assert len(settings.current.cards) == 2
    assert scenario_aliases <= configured_aliases
    assert settings.current.cards[0].alias == "is_bankasi_troy_1396"
    assert settings.current.cards[0].expected_otp is not None


def test_build_credential_runtime_config_json_serializes_valid_settings(tmp_path: Path) -> None:
    paynkolay_cards = tmp_path / "paynkolay_merchants.csv"
    paynkolay_cards.write_text(
        "\ufeffBanka Adi,Kart Numarasi,Kart Semasi,Son Kullanma Tarihi,CVC Kodu,Sifre\n"
        "DenizBank,5200190006338608,MasterCard,2030/01,410,123456\n",
        encoding="utf-8",
    )

    body = build_credential_runtime_config_json(paynkolay_cards_path=paynkolay_cards)
    settings = RuntimeSettings.model_validate_json(body)

    assert settings.current.name == "dev"
    assert settings.current.cards[0].alias == "denizbank_mastercard_8608"
    assert settings.current.cards[0].requires_3ds is True


def test_build_credential_runtime_config_rejects_empty_card_set() -> None:
    with pytest.raises(ValueError, match="at least one credential card"):
        build_credential_runtime_config_payload()
