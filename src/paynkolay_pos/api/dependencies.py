"""Shared dependencies and filesystem paths for the FastAPI app."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol, cast

from fastapi import HTTPException, Request, status
from pydantic import SecretStr

from paynkolay_pos.api.parallel_run_store import ParallelRunStore
from paynkolay_pos.api.payment_initializer import (
    PaynkolayPaymentInitializer,
    SupportsPaymentInitializer,
)
from paynkolay_pos.api.session_store import PaymentSessionStore
from paynkolay_pos.api.three_ds_store import ThreeDSFormStore
from paynkolay_pos.clients import PaynkolayClient
from paynkolay_pos.config import load_runtime_settings
from paynkolay_pos.config.settings import CardBrand
from paynkolay_pos.reporting import (
    SupportsExternalPaymentLogger,
    external_logger_from_env,
)
from paynkolay_pos.three_ds import AcsBrowserAutomationResult, complete_acs_browser_challenge


class SupportsThreeDSAutomator(Protocol):
    """Behavior required to complete ACS browser challenges."""

    async def complete(
        self,
        *,
        html: str,
        brand: CardBrand,
        configured_otp: SecretStr | None,
        callback_url: str,
    ) -> AcsBrowserAutomationResult:
        """Complete a 3DS challenge and return sanitized evidence."""


class PlaywrightThreeDSAutomator:
    """Default server-side Playwright automator."""

    def __init__(self, *, form_base_url: str) -> None:
        self._form_base_url = form_base_url

    async def complete(
        self,
        *,
        html: str,
        brand: CardBrand,
        configured_otp: SecretStr | None,
        callback_url: str,
    ) -> AcsBrowserAutomationResult:
        """Complete a 3DS challenge using Chromium."""

        return await complete_acs_browser_challenge(
            html=html,
            brand=brand,
            configured_otp=configured_otp,
            callback_url=callback_url,
            form_base_url=self._form_base_url,
        )


def package_root() -> Path:
    """Return the installed package root directory."""

    return Path(__file__).resolve().parents[1]


def web_root() -> Path:
    """Return the packaged web asset root directory."""

    return package_root() / "web"


def templates_dir() -> Path:
    """Return the Jinja template directory."""

    return web_root() / "templates"


def static_dir() -> Path:
    """Return the static asset directory."""

    return web_root() / "static"


def allure_report_dir() -> Path:
    """Return the local Allure HTML report directory."""

    return Path(os.getenv("PAYNKOLAY_ALLURE_REPORT_DIR", "allure-report"))


def allure_results_dir() -> Path:
    """Return the local Allure raw results directory."""

    return Path(os.getenv("PAYNKOLAY_ALLURE_RESULTS_DIR", "allure-results"))


def get_payment_session_store(request: Request) -> PaymentSessionStore:
    """Return the app-scoped in-memory payment session store."""

    return cast(PaymentSessionStore, request.app.state.payment_session_store)


def get_three_ds_form_store(request: Request) -> ThreeDSFormStore:
    """Return the app-scoped transient 3DS form store."""

    return cast(ThreeDSFormStore, request.app.state.three_ds_form_store)


def get_parallel_run_store(request: Request) -> ParallelRunStore:
    """Return the app-scoped in-memory parallel run store."""

    return cast(ParallelRunStore, request.app.state.parallel_run_store)


def get_three_ds_automator() -> SupportsThreeDSAutomator:
    """Return the configured 3DS browser automator."""

    return PlaywrightThreeDSAutomator(
        form_base_url=os.getenv(
            "PAYNKOLAY_UAT_3DS_FORM_BASE_URL",
            "https://vpostest.qnb.com.tr/PayforACSSimulator/",
        )
    )


async def get_payment_initializer() -> AsyncIterator[SupportsPaymentInitializer]:
    """Return a configured provider initializer for live payment attempts."""

    try:
        environment = load_runtime_settings().current
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"runtime payment configuration is unavailable: {exc}",
        ) from exc

    async with PaynkolayClient(environment) as client:
        yield PaynkolayPaymentInitializer(
            environment=environment,
            client=client,
        )


def get_merchant_secret_key() -> SecretStr:
    """Return the active merchant secret key for provider return verification."""

    try:
        return load_runtime_settings().current.merchant.secret_key
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"runtime payment configuration is unavailable: {exc}",
        ) from exc


def get_external_payment_logger() -> SupportsExternalPaymentLogger:
    """Return the configured external payment logger."""

    return external_logger_from_env()
