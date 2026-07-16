from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from paynkolay_pos.config import TestCard as ConfigTestCard


def _load_uat_parallel_3ds_smoke_module() -> ModuleType:
    script_path = Path(__file__).parents[2] / "tools" / "run_uat_parallel_3ds_smoke.py"
    spec = importlib.util.spec_from_file_location("run_uat_parallel_3ds_smoke", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


UAT_PARALLEL_3DS_SMOKE = _load_uat_parallel_3ds_smoke_module()


def test_parse_manual_cards_builds_repeat_selections() -> None:
    selections = UAT_PARALLEL_3DS_SMOKE._parse_manual_cards(
        (
            "nkolay_dynamic_otp_visa_6111:5",
            "garanti_bankasi_mastercard_6017:5",
        )
    )

    assert selections == [
        {"alias": "nkolay_dynamic_otp_visa_6111", "repeat_count": 5},
        {"alias": "garanti_bankasi_mastercard_6017", "repeat_count": 5},
    ]


def test_parse_manual_cards_rejects_invalid_format() -> None:
    with pytest.raises(SystemExit, match="ALIAS:COUNT"):
        UAT_PARALLEL_3DS_SMOKE._parse_manual_cards(("missing-count",))


def test_select_manual_3ds_cards_validates_aliases_and_flow() -> None:
    selected = UAT_PARALLEL_3DS_SMOKE._select_manual_3ds_cards(
        (
            _card("nkolay_dynamic_otp_visa_6111", requires_3ds=True),
            _card("garanti_bankasi_mastercard_6017", requires_3ds=True),
        ),
        manual_cards=[
            {"alias": "nkolay_dynamic_otp_visa_6111", "repeat_count": 5},
            {"alias": "garanti_bankasi_mastercard_6017", "repeat_count": 5},
        ],
    )

    assert selected == [
        {"alias": "nkolay_dynamic_otp_visa_6111", "repeat_count": 5},
        {"alias": "garanti_bankasi_mastercard_6017", "repeat_count": 5},
    ]


def test_select_manual_3ds_cards_rejects_moto_card() -> None:
    with pytest.raises(SystemExit, match="does not require 3DS"):
        UAT_PARALLEL_3DS_SMOKE._select_manual_3ds_cards(
            (_card("moto_card", requires_3ds=False),),
            manual_cards=[{"alias": "moto_card", "repeat_count": 1}],
        )


def _card(alias: str, *, requires_3ds: bool) -> ConfigTestCard:
    payload: dict[str, object] = {
        "alias": alias,
        "brand": "visa",
        "pan": "4111111111111111",
        "expiry_month": 12,
        "expiry_year": 2030,
        "cvv": "123",
        "requires_3ds": requires_3ds,
    }
    if requires_3ds:
        payload["expected_otp"] = "123456"
    return ConfigTestCard.model_validate(payload)
