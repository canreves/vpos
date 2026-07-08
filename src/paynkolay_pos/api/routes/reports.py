"""Report metadata routes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from paynkolay_pos.api.dependencies import allure_report_dir, allure_results_dir
from paynkolay_pos.api.schemas import (
    ReportHistoryResponse,
    ReportRunSummary,
    ReportStatusResponse,
    ReportTestResultSummary,
)

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


@router.get("/history", response_model=ReportHistoryResponse)
async def report_history() -> ReportHistoryResponse:
    """Return a safe summary of the latest local Allure result files."""

    results_dir = allure_results_dir()
    if not results_dir.is_dir():
        return ReportHistoryResponse(
            available=False,
            results_path=str(results_dir),
            message="Allure results have not been generated yet.",
        )

    test_results = _read_result_files(results_dir)
    if not test_results:
        return ReportHistoryResponse(
            available=False,
            results_path=str(results_dir),
            message="No Allure test result files were found.",
        )

    latest = _run_summary(test_results)
    return ReportHistoryResponse(
        available=True,
        results_path=str(results_dir),
        latest=latest,
        message="Latest local test run summary is available.",
    )


def _read_result_files(results_dir: Path) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for path in sorted(results_dir.glob("*-result.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _run_summary(test_results: list[dict[str, Any]]) -> ReportRunSummary:
    status_counts = {
        "passed": 0,
        "failed": 0,
        "broken": 0,
        "skipped": 0,
        "unknown": 0,
    }
    starts: list[int] = []
    stops: list[int] = []
    recent_tests: list[ReportTestResultSummary] = []
    for result in test_results:
        status = str(result.get("status") or "unknown")
        if status not in status_counts:
            status = "unknown"
        status_counts[status] += 1

        start = _timestamp_ms(result.get("start"))
        stop = _timestamp_ms(result.get("stop"))
        if start is not None:
            starts.append(start)
        if stop is not None:
            stops.append(stop)
        recent_tests.append(_test_summary(result, start=start, stop=stop))

    recent_tests.sort(key=lambda test: test.started_at or "", reverse=True)
    started_at = min(starts) if starts else None
    finished_at = max(stops) if stops else None
    return ReportRunSummary(
        total=len(test_results),
        passed=status_counts["passed"],
        failed=status_counts["failed"],
        broken=status_counts["broken"],
        skipped=status_counts["skipped"],
        unknown=status_counts["unknown"],
        started_at=_format_timestamp_ms(started_at),
        finished_at=_format_timestamp_ms(finished_at),
        duration_ms=(finished_at - started_at)
        if started_at is not None and finished_at is not None
        else None,
        recent_tests=recent_tests[:10],
    )


def _test_summary(
    result: dict[str, Any],
    *,
    start: int | None,
    stop: int | None,
) -> ReportTestResultSummary:
    return ReportTestResultSummary(
        name=str(result.get("name") or "unknown test"),
        status=str(result.get("status") or "unknown"),
        suite=_label_value(result, "suite"),
        duration_ms=(stop - start) if start is not None and stop is not None else None,
        started_at=_format_timestamp_ms(start),
    )


def _label_value(result: dict[str, Any], name: str) -> str | None:
    labels = result.get("labels")
    if not isinstance(labels, list):
        return None
    for label in labels:
        if not isinstance(label, dict):
            continue
        if label.get("name") == name and label.get("value"):
            return str(label["value"])
    return None


def _timestamp_ms(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _format_timestamp_ms(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat()
