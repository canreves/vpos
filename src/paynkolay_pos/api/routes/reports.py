"""Report metadata routes."""

from __future__ import annotations

from fastapi import APIRouter

from paynkolay_pos.api.dependencies import allure_report_dir
from paynkolay_pos.api.schemas import ReportStatusResponse

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/latest", response_model=ReportStatusResponse)
async def latest_report() -> ReportStatusResponse:
    """Return local Allure HTML report availability."""

    report_dir = allure_report_dir()
    entrypoint = report_dir / "index.html"
    if entrypoint.is_file():
        return ReportStatusResponse(
            available=True,
            report_path=str(report_dir),
            entrypoint=str(entrypoint),
            message="Allure HTML report is available.",
        )
    return ReportStatusResponse(
        available=False,
        report_path=str(report_dir),
        message="Allure HTML report has not been generated yet.",
    )

