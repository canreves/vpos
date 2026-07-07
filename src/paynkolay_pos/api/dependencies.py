"""Shared dependencies and filesystem paths for the FastAPI app."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

from fastapi import HTTPException, Request, status

from paynkolay_pos.api.payment_initializer import (
    PaynkolayPaymentInitializer,
    SupportsPaymentInitializer,
)
from paynkolay_pos.api.session_store import PaymentSessionStore
from paynkolay_pos.clients import PaynkolayClient
from paynkolay_pos.config import load_runtime_settings


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


def get_payment_session_store(request: Request) -> PaymentSessionStore:
    """Return the app-scoped in-memory payment session store."""

    return cast(PaymentSessionStore, request.app.state.payment_session_store)


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
