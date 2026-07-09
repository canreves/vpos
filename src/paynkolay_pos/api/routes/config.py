"""Runtime metadata routes for the browser UI."""

from __future__ import annotations

import os
from collections import Counter

from fastapi import APIRouter

from paynkolay_pos.api.schemas import (
    ConfigCardSummary,
    ConfigMerchantSummary,
    ConfigOverviewResponse,
    ConfigReadinessIssueSummary,
    ConfigReadinessSummary,
    ConfigResponse,
    ConfigScenarioCoverage,
    ConfigScenarioSummary,
)
from paynkolay_pos.config import CardBrand, load_runtime_settings
from paynkolay_pos.models import Currency, PaymentChannel
from paynkolay_pos.sandbox import check_sandbox_readiness
from paynkolay_pos.scenarios import (
    PaymentScenarioCatalog,
    load_payment_scenario_catalog_from_env,
    scenario_catalog_path_from_env,
)

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", response_model=ConfigResponse)
async def get_config() -> ConfigResponse:
    """Return safe runtime configuration metadata for the browser."""

    supported_currencies = [currency.value for currency in Currency]
    supported_card_brands = [brand.value for brand in CardBrand]
    payment_channels = [channel.value for channel in PaymentChannel]

    try:
        settings = load_runtime_settings()
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return ConfigResponse(
            runtime_configured=False,
            supported_currencies=supported_currencies,
            supported_card_brands=supported_card_brands,
            payment_channels=payment_channels,
            message=str(exc),
        )

    current = settings.current
    return ConfigResponse(
        runtime_configured=True,
        active_environment=current.name.value,
        supported_currencies=supported_currencies,
        supported_card_brands=supported_card_brands,
        payment_channels=payment_channels,
        card_aliases=[card.alias for card in current.cards],
    )


@router.get("/overview", response_model=ConfigOverviewResponse)
async def get_config_overview() -> ConfigOverviewResponse:
    """Return safe runtime, scenario, and readiness metadata for testers."""

    config_source = os.getenv("PAYNKOLAY_CONFIG_FILE")
    try:
        settings = load_runtime_settings()
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return ConfigOverviewResponse(
            runtime_configured=False,
            config_source=config_source,
            scenarios=_scenario_summary_without_runtime(),
            readiness=ConfigReadinessSummary(
                checked=False,
                message="Runtime config is required before readiness can be checked.",
            ),
            message=str(exc),
        )

    current = settings.current
    scenario_summary, catalog = _scenario_summary()
    readiness = ConfigReadinessSummary(
        checked=False,
        message="Scenario catalogue is required before readiness can be checked.",
    )
    if catalog is not None:
        report = check_sandbox_readiness(settings, catalog)
        readiness = ConfigReadinessSummary(
            checked=True,
            ready=report.ready,
            issue_count=len(report.issues),
            issues=[
                ConfigReadinessIssueSummary(code=issue.code, message=issue.message)
                for issue in report.issues
            ],
        )

    return ConfigOverviewResponse(
        runtime_configured=True,
        active_environment=current.name.value,
        config_source=config_source,
        base_url_configured=True,
        callback_configured=True,
        merchant=ConfigMerchantSummary(
            merchant_id=_mask_value(current.merchant.merchant_id),
            terminal_id=_mask_value(current.merchant.terminal_id),
            has_list_key=current.merchant.list_api_key is not None,
            has_cancel_refund_key=current.merchant.cancel_refund_api_key is not None,
        ),
        card_count=len(current.cards),
        cards=[
            ConfigCardSummary(
                alias=card.alias,
                brand=card.brand.value,
                requires_3ds=card.requires_3ds,
                has_expected_otp=card.expected_otp is not None,
            )
            for card in current.cards
        ],
        scenarios=scenario_summary,
        readiness=readiness,
    )


def _scenario_summary() -> tuple[ConfigScenarioSummary, PaymentScenarioCatalog | None]:
    source = str(scenario_catalog_path_from_env())
    try:
        catalog = load_payment_scenario_catalog_from_env()
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return (
            ConfigScenarioSummary(
                configured=False,
                source=source,
                message=str(exc),
            ),
            None,
        )

    tags = sorted({tag for scenario in catalog.scenarios for tag in scenario.tags})
    return (
        ConfigScenarioSummary(
            configured=True,
            source=source,
            scenario_count=len(catalog.scenarios),
            tags=tags,
            coverage=_scenario_coverage(catalog),
        ),
        catalog,
    )


def _scenario_summary_without_runtime() -> ConfigScenarioSummary:
    source = str(scenario_catalog_path_from_env())
    try:
        catalog = load_payment_scenario_catalog_from_env()
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return ConfigScenarioSummary(configured=False, source=source, message=str(exc))

    tags = sorted({tag for scenario in catalog.scenarios for tag in scenario.tags})
    return ConfigScenarioSummary(
        configured=True,
        source=source,
        scenario_count=len(catalog.scenarios),
        tags=tags,
        coverage=_scenario_coverage(catalog),
    )


def _scenario_coverage(catalog: PaymentScenarioCatalog) -> ConfigScenarioCoverage:
    payment_channels = Counter(scenario.payment_channel.value for scenario in catalog.scenarios)
    final_statuses = Counter(scenario.expected_final_status.value for scenario in catalog.scenarios)
    installments = Counter(str(scenario.installment_count) for scenario in catalog.scenarios)
    error_codes = Counter(
        tag.removeprefix("error_code_")
        for scenario in catalog.scenarios
        for tag in scenario.tags
        if tag.startswith("error_code_")
    )
    return ConfigScenarioCoverage(
        three_ds_count=sum(1 for scenario in catalog.scenarios if scenario.requires_3ds),
        moto_count=sum(1 for scenario in catalog.scenarios if scenario.moto),
        single_payment_count=sum(
            1 for scenario in catalog.scenarios if scenario.installment_count == 1
        ),
        installment_count=sum(
            1 for scenario in catalog.scenarios if scenario.installment_count > 1
        ),
        negative_count=sum(1 for scenario in catalog.scenarios if "negative" in scenario.tags),
        payment_channel_counts=dict(sorted(payment_channels.items())),
        final_status_counts=dict(sorted(final_statuses.items())),
        installment_counts=dict(sorted(installments.items(), key=lambda item: int(item[0]))),
        error_code_counts=dict(sorted(error_codes.items())),
    )


def _mask_value(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * max(len(value) - 4, 4)}{value[-2:]}"
