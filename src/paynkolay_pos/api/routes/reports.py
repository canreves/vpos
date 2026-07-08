"""Report metadata routes."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from paynkolay_pos.api.dependencies import allure_report_dir, allure_results_dir
from paynkolay_pos.api.schemas import (
    ReportCommandRunResponse,
    ReportHistoryResponse,
    ReportRunSummary,
    ReportStatusResponse,
    ReportTestResultSummary,
)

router = APIRouter(prefix="/api/reports", tags=["reports"])
DEFAULT_CREDENTIAL_REPORT_COMMAND = ("make", "credential-scenario-report")
OUTPUT_TAIL_LIMIT = 4000
ReportCommandStatus = Literal["idle", "running", "passed", "failed"]


@dataclass
class ReportCommandRunState:
    """In-memory state for one fixed local report command."""

    command: tuple[str, ...] = DEFAULT_CREDENTIAL_REPORT_COMMAND
    status: ReportCommandStatus = "idle"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    exit_code: int | None = None
    output_tail: str | None = None
    _lock: Lock = field(default_factory=Lock, repr=False)

    def start(self) -> ReportCommandRunResponse:
        with self._lock:
            if self.status == "running":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="credential report run is already running",
                )
            self.status = "running"
            self.started_at = datetime.now(tz=UTC)
            self.finished_at = None
            self.exit_code = None
            self.output_tail = None
            return self.snapshot(message="Credential report run started.")

    def finish(self, *, exit_code: int, output: str) -> None:
        with self._lock:
            self.status = "passed" if exit_code == 0 else "failed"
            self.finished_at = datetime.now(tz=UTC)
            self.exit_code = exit_code
            self.output_tail = output[-OUTPUT_TAIL_LIMIT:] or None

    def snapshot(self, *, message: str | None = None) -> ReportCommandRunResponse:
        return ReportCommandRunResponse(
            status=self.status,
            command=list(self.command),
            started_at=_format_datetime(self.started_at),
            finished_at=_format_datetime(self.finished_at),
            exit_code=self.exit_code,
            output_tail=self.output_tail,
            message=message or _command_message(self.status),
        )


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


@router.get("/credential-run", response_model=ReportCommandRunResponse)
async def credential_report_run_status(request: Request) -> ReportCommandRunResponse:
    """Return the current local credential report command status."""

    return _report_command_state(request).snapshot()


@router.post(
    "/credential-run",
    response_model=ReportCommandRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_credential_report_run(
    request: Request,
    background_tasks: BackgroundTasks,
) -> ReportCommandRunResponse:
    """Start the fixed local credential scenario report command."""

    run_state = _report_command_state(request)
    response = run_state.start()
    background_tasks.add_task(_execute_credential_report_run, run_state)
    return response


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


def _report_command_state(request: Request) -> ReportCommandRunState:
    state = request.app.state.credential_report_run
    if not isinstance(state, ReportCommandRunState):
        raise RuntimeError("credential report run state is not configured")
    return state


def _execute_credential_report_run(run_state: ReportCommandRunState) -> None:
    result = _run_command(run_state.command)
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    run_state.finish(exit_code=result.returncode, output=output)


def _run_command(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
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


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _command_message(run_status: ReportCommandStatus) -> str:
    if run_status == "idle":
        return "Credential report run has not been started from this web session."
    if run_status == "running":
        return "Credential report run is still running."
    if run_status == "passed":
        return "Credential report run completed successfully."
    return "Credential report run failed. Review the output tail."
