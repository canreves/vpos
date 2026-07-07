"""Shared dependencies and filesystem paths for the FastAPI app."""

from __future__ import annotations

import os
from pathlib import Path


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

