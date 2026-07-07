"""FastAPI application factory for the Paynkolay POS web UI."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from paynkolay_pos.api.dependencies import static_dir, templates_dir
from paynkolay_pos.api.routes import config, health, payments, reports


def create_app() -> FastAPI:
    """Create and configure the FastAPI web application."""

    app = FastAPI(
        title="Paynkolay Sanal POS Web",
        version="0.1.0",
        description="Browser UI and API surface for Paynkolay Sanal POS testing.",
    )
    app.mount("/static", StaticFiles(directory=static_dir()), name="static")

    templates = Jinja2Templates(directory=templates_dir())

    @app.get("/", include_in_schema=False)
    async def payment_page(request: Request) -> Response:
        return templates.TemplateResponse(
            request,
            "payment.html",
            {"title": "Payment"},
        )

    @app.get("/result", include_in_schema=False)
    async def result_page(request: Request) -> Response:
        return templates.TemplateResponse(
            request,
            "result.html",
            {"title": "Result"},
        )

    @app.get("/reports", include_in_schema=False)
    async def reports_page(request: Request) -> Response:
        return templates.TemplateResponse(
            request,
            "report.html",
            {"title": "Reports"},
        )

    app.include_router(health.router)
    app.include_router(config.router)
    app.include_router(payments.router)
    app.include_router(reports.router)
    return app
