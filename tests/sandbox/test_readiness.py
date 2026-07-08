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
    expected_initialize_status: str = "pending_3ds",
    expected_final_status: str = "captured",
    installment_count: int = 1,
    tags: list[str] | None = None,
) -> PaymentScenario:
    effective_tags = tags or (["sandbox", "moto"] if moto else ["sandbox", "three_ds"])
    return PaymentScenario.model_validate(
        {
            "scenario_id": scenario_id,
            "title": scenario_id.replace("_", " ").title(),
            "card_alias": card_alias,
            "amount": "100.00",
            "currency": "TRY",
            "requires_3ds": requires_3ds,
            "expected_initialize_status": expected_initialize_status,
            "expected_final_status": expected_final_status,
            "installment_count": installment_count,
            "payment_channel": "moto" if moto else "e_commerce",
            "moto": moto,
            "tags": effective_tags,
        }
    )


@pytest.mark.sandbox
def test_check_sandbox_readiness_accepts_ready_private_inputs() -> None:
    scenarios = (
        scenario(
            "sandbox_3ds_capture",
            card_alias="sandbox_3ds_success",
            tags=["sandbox", "three_ds", "credit"],
        ),
        scenario(
            "sandbox_3ds_declined",
            card_alias="sandbox_3ds_declined",
            expected_final_status="failed",
            tags=["sandbox", "three_ds", "negative"],
        ),
        scenario(
            "sandbox_3ds_wrong_otp",
            card_alias="sandbox_3ds_wrong_otp",
            expected_final_status="failed",
            tags=["sandbox", "three_ds", "negative", "wrong_otp"],
        ),
        scenario(
            "sandbox_invalid_cvv",
            card_alias="sandbox_invalid_cvv",
            expected_initialize_status="failed",
            expected_final_status="failed",
            tags=["sandbox", "negative", "invalid_cvv"],
        ),
        scenario(
            "sandbox_expired_card",
            card_alias="sandbox_expired_card",
            expected_initialize_status="failed",
            expected_final_status="failed",
            tags=["sandbox", "negative", "expired_card"],
        ),
        scenario(
            "sandbox_insufficient_funds",
            card_alias="sandbox_insufficient_funds",
            expected_final_status="failed",
            tags=["sandbox", "three_ds", "negative", "insufficient_funds"],
        ),
        scenario(
            "sandbox_moto_authorized",
            card_alias="sandbox_moto_success",
            requires_3ds=False,
            moto=True,
            expected_initialize_status="authorized",
            expected_final_status="authorized",
            tags=["sandbox", "moto"],
        ),
        scenario(
            "sandbox_moto_declined",
            card_alias="sandbox_moto_declined",
            requires_3ds=False,
            moto=True,
            expected_initialize_status="failed",
            expected_final_status="failed",
            tags=["sandbox", "moto", "negative"],
        ),
        scenario(
            "sandbox_payment_list_missing",
            card_alias="sandbox_payment_list_success",
            expected_final_status="failed",
            tags=["sandbox", "negative", "payment_list"],
        ),
        scenario(
            "sandbox_debit_3ds_capture",
            card_alias="sandbox_debit_3ds_success",
            tags=["sandbox", "three_ds", "debit"],
        ),
        scenario(
            "sandbox_installment_2_capture",
            card_alias="sandbox_installment_2_success",
            installment_count=2,
            tags=["sandbox", "three_ds", "installment"],
        ),
        scenario(
            "sandbox_installment_3_capture",
            card_alias="sandbox_installment_3_success",
            installment_count=3,
            tags=["sandbox", "three_ds", "installment"],
        ),
        scenario(
            "sandbox_installment_6_capture",
            card_alias="sandbox_installment_6_success",
            installment_count=6,
            tags=["sandbox", "three_ds", "installment"],
        ),
        scenario(
            "sandbox_installment_9_capture",
            card_alias="sandbox_installment_9_success",
            installment_count=9,
            tags=["sandbox", "three_ds", "installment"],
        ),
        scenario(
            "sandbox_installment_12_capture",
            card_alias="sandbox_installment_12_success",
            installment_count=12,
            tags=["sandbox", "three_ds", "installment"],
        ),
        scenario(
            "sandbox_cancel_success",
            card_alias="sandbox_cancel_success",
            expected_final_status="cancelled",
            tags=["sandbox", "three_ds", "cancel"],
        ),
        scenario(
            "sandbox_refund_success",
            card_alias="sandbox_refund_success",
            expected_final_status="refunded",
            tags=["sandbox", "three_ds", "refund"],
        ),
    )
    scenario_aliases = {item.card_alias for item in scenarios}
    settings = RuntimeSettings.model_validate(
        runtime_settings_payload(
            cards=[
                card_payload(
                    alias,
                    requires_3ds=not alias.startswith("sandbox_moto"),
                )
                for alias in sorted(scenario_aliases)
            ]
        )
    )
    catalog = PaymentScenarioCatalog(scenarios=scenarios)

    report = check_sandbox_readiness(settings, catalog, minimum_card_count=len(scenario_aliases))

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
        "missing_moto_success_scenario",
        "missing_moto_negative_scenario",
        "missing_wrong_otp_scenario",
        "missing_invalid_cvv_scenario",
        "missing_expired_card_scenario",
        "missing_insufficient_funds_scenario",
        "missing_payment_list_scenario",
        "missing_debit_scenario",
        "missing_credit_scenario",
        "missing_cancel_scenario",
        "missing_refund_scenario",
        "missing_installment_scenarios",
    } <= issue_codes
    assert "Sandbox readiness: NOT READY" in format_readiness_report(report)


@pytest.mark.sandbox
@pytest.mark.negative
def test_check_sandbox_readiness_reports_scenario_card_3ds_mismatch() -> None:
    settings = RuntimeSettings.model_validate(
        runtime_settings_payload(cards=[card_payload("moto_only_card", requires_3ds=False)])
    )
    catalog = PaymentScenarioCatalog(
        scenarios=(
            scenario("sandbox_3ds_capture", card_alias="moto_only_card"),
        )
    )

    report = check_sandbox_readiness(settings, catalog, minimum_card_count=1)
    issue_codes = {issue.code for issue in report.issues}

    assert "scenario_card_3ds_mismatch" in issue_codes


@pytest.mark.sandbox
@pytest.mark.negative
def test_check_sandbox_readiness_reports_moto_bound_to_3ds_card() -> None:
    settings = RuntimeSettings.model_validate(
        runtime_settings_payload(cards=[card_payload("three_ds_card", requires_3ds=True)])
    )
    catalog = PaymentScenarioCatalog(
        scenarios=(
            scenario(
                "sandbox_moto_authorized",
                card_alias="three_ds_card",
                requires_3ds=False,
                moto=True,
                expected_initialize_status="authorized",
                expected_final_status="authorized",
                tags=["sandbox", "moto"],
            ),
        )
    )

    report = check_sandbox_readiness(settings, catalog, minimum_card_count=1)
    issue_codes = {issue.code for issue in report.issues}

    assert "scenario_card_3ds_mismatch" in issue_codes
    assert "moto_card_requires_3ds" in issue_codes


@pytest.mark.sandbox
@pytest.mark.negative
def test_check_sandbox_readiness_reports_missing_3ds_families() -> None:
    settings = RuntimeSettings.model_validate(
        runtime_settings_payload(cards=[card_payload("sandbox_moto_success", requires_3ds=False)])
    )
    catalog = PaymentScenarioCatalog(
        scenarios=(
            scenario(
                "sandbox_moto_authorized",
                card_alias="sandbox_moto_success",
                requires_3ds=False,
                moto=True,
                expected_initialize_status="authorized",
                expected_final_status="authorized",
                tags=["sandbox", "moto"],
            ),
        )
    )

    report = check_sandbox_readiness(settings, catalog, minimum_card_count=1)
    issue_codes = {issue.code for issue in report.issues}

    assert "missing_3ds_success_scenario" in issue_codes
    assert "missing_3ds_negative_scenario" in issue_codes
