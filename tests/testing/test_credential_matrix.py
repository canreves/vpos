from __future__ import annotations

import json
from pathlib import Path

from paynkolay_pos.testing import build_credential_matrix_json, build_credential_matrix_payload


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
