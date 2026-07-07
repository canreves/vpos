from __future__ import annotations

import pytest

from paynkolay_pos.config import RuntimeSettings
from paynkolay_pos.sandbox import check_sandbox_readiness, format_readiness_report
from paynkolay_pos.scenarios import PaymentScenarioCatalog
from paynkolay_pos.scenarios.payments import PaymentScenario


def runtime_settings_payload(*, cards: list[dict[str, object]]) -> dict[str, object]:
    return {
        "active_environment": "uat",
        "environments": {
            "uat": {
                "name": "uat",
                "base_url": "https://sandbox.paynkolay.test/Vpos",
                "callback_base_url": "https://merchant-callback.test/callbacks",
                "merchant": {
                    "merchant_id": "merchant-1001",
                    "terminal_id": "terminal-1001",
                    "api_key": "payment-sx-1001",
                    "cancel_refund_api_key": "refund-sx-1001",
                    "secret_key": "secret-1001",
                },
                "cards": cards,
            }
        },
    }


def card_payload(alias: str, *, requires_3ds: bool = True) -> dict[str, object]:
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
    return payload


def scenario(
    scenario_id: str,
    *,
    card_alias: str,
    requires_3ds: bool = True,
    moto: bool = False,
) -> PaymentScenario:
    return PaymentScenario.model_validate(
        {
            "scenario_id": scenario_id,
            "title": scenario_id.replace("_", " ").title(),
            "card_alias": card_alias,
            "amount": "100.00",
            "currency": "TRY",
            "requires_3ds": requires_3ds,
            "expected_initialize_status": "pending_3ds" if requires_3ds else "authorized",
            "expected_final_status": "captured" if requires_3ds else "authorized",
            "payment_channel": "moto" if moto else "e_commerce",
            "moto": moto,
            "tags": ["sandbox", "moto"] if moto else ["sandbox", "three_ds"],
        }
    )


@pytest.mark.sandbox
def test_check_sandbox_readiness_accepts_ready_private_inputs() -> None:
    settings = RuntimeSettings.model_validate(
        runtime_settings_payload(
            cards=[
                card_payload("sandbox_3ds_success"),
                card_payload("sandbox_moto_success", requires_3ds=False),
            ]
        )
    )
    catalog = PaymentScenarioCatalog(
        scenarios=(
            scenario("sandbox_3ds_capture", card_alias="sandbox_3ds_success"),
            scenario(
                "sandbox_moto_authorized",
                card_alias="sandbox_moto_success",
                requires_3ds=False,
                moto=True,
            ),
        )
    )

    report = check_sandbox_readiness(settings, catalog, minimum_card_count=2)

    assert report.ready is True
    assert format_readiness_report(report).startswith("Sandbox readiness: READY")


@pytest.mark.sandbox
@pytest.mark.negative
def test_check_sandbox_readiness_reports_actionable_issues() -> None:
    settings = RuntimeSettings.model_validate(
        {
            "active_environment": "uat",
            "environments": {
                "uat": {
                    "name": "uat",
                    "base_url": "https://sandbox.paynkolay.test/Vpos",
                    "callback_base_url": "https://merchant-uat.example.test",
                    "merchant": {
                        "merchant_id": "replace-with-merchant-id",
                        "terminal_id": "terminal-1001",
                        "api_key": "payment-sx-1001",
                        "secret_key": "secret-1001",
                    },
                    "cards": [card_payload("configured_card")],
                }
            },
        }
    )
    catalog = PaymentScenarioCatalog(
        scenarios=(
            scenario("sandbox_3ds_capture", card_alias="missing_card"),
        )
    )

    report = check_sandbox_readiness(settings, catalog)
    issue_codes = {issue.code for issue in report.issues}

    assert report.ready is False
    assert {
        "placeholder_value",
        "insufficient_cards",
        "missing_card_aliases",
        "unused_card_aliases",
    } <= issue_codes
    assert "Sandbox readiness: NOT READY" in format_readiness_report(report)
