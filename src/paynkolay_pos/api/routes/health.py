"""Health check route."""

from __future__ import annotations

from fastapi import APIRouter

from paynkolay_pos.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return a lightweight health check payload."""

    return HealthResponse(
        status="ok",
        service="paynkolay-pos-web",
        version="0.1.0",
    )

