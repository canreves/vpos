"""In-memory state for browser-triggered parallel payment runs."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from paynkolay_pos.api.schemas import (
    ParallelRunItemAutomationStatus,
    ParallelRunItemResponse,
    ParallelRunResponse,
    PaymentListStatusSummary,
)
from paynkolay_pos.api.session_models import ProviderRequestSummary, ThreeDSAutomationSummary

ParallelRunStatus = Literal["pending", "running", "completed", "completed_with_failures", "failed"]
ParallelRunItemStatus = Literal["pending", "running", "completed", "failed"]


@dataclass
class ParallelRunItemState:
    """Mutable state for one payment attempt in a parallel run."""

    item_id: str
    card_alias: str
    attempt_index: int
    order_id: str
    requires_3ds: bool
    automation_status: ParallelRunItemAutomationStatus
    automation_reason: str
    diagnostic_class: str
    automatic_success_candidate: bool
    status: ParallelRunItemStatus = "pending"
    classification: str = "pending"
    provider_request: ProviderRequestSummary | None = None
    provider_response_code: str | None = None
    provider_response_data: str | None = None
    payment_list: PaymentListStatusSummary | None = None
    payment_list_status: str | None = None
    payment_list_error: str | None = None
    three_ds_automation: ThreeDSAutomationSummary | None = None
    error_message: str | None = None
    three_ds_url: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def duration_ms(self) -> int | None:
        """Return item duration in milliseconds when the item has finished."""

        if self.started_at is None or self.finished_at is None:
            return None
        return int((self.finished_at - self.started_at).total_seconds() * 1000)

    def response(self) -> ParallelRunItemResponse:
        """Return a serialized item response."""

        return ParallelRunItemResponse(
            item_id=self.item_id,
            card_alias=self.card_alias,
            attempt_index=self.attempt_index,
            order_id=self.order_id,
            status=self.status,
            classification=self.classification,
            requires_3ds=self.requires_3ds,
            automation_status=self.automation_status,
            automation_reason=self.automation_reason,
            diagnostic_class=self.diagnostic_class,
            automatic_success_candidate=self.automatic_success_candidate,
            provider_request=self.provider_request,
            provider_response_code=self.provider_response_code,
            provider_response_data=self.provider_response_data,
            payment_list=self.payment_list,
            payment_list_status=self.payment_list_status,
            payment_list_error=self.payment_list_error,
            three_ds_automation=self.three_ds_automation,
            error_message=self.error_message,
            duration_ms=self.duration_ms,
            three_ds_url=self.three_ds_url,
        )


@dataclass
class ParallelRunState:
    """Mutable state for one browser-triggered parallel run."""

    run_id: str
    mode: Literal["manual", "random"]
    concurrency: int
    items: list[ParallelRunItemState]
    status: ParallelRunStatus = "pending"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    evidence_path: str | None = None
    message: str = "Parallel run is pending."

    def response(self, *, include_items: bool = True) -> ParallelRunResponse:
        """Return a serialized run response."""

        completed = sum(1 for item in self.items if item.status == "completed")
        failed = sum(1 for item in self.items if item.status == "failed")
        return ParallelRunResponse(
            run_id=self.run_id,
            mode=self.mode,
            status=self.status,
            concurrency=self.concurrency,
            total=len(self.items),
            completed=completed,
            failed=failed,
            started_at=_format_datetime(self.started_at),
            finished_at=_format_datetime(self.finished_at),
            evidence_path=self.evidence_path,
            message=self.message,
            items=[item.response() for item in self.items] if include_items else [],
        )


class ParallelRunNotFoundError(KeyError):
    """Raised when a parallel run ID is not tracked."""


class ParallelRunStore:
    """Small async in-memory store for parallel payment run state."""

    def __init__(self) -> None:
        self._runs: dict[str, ParallelRunState] = {}
        self._lock = asyncio.Lock()

    async def create(self, run: ParallelRunState) -> ParallelRunState:
        """Store a new run."""

        async with self._lock:
            self._runs[run.run_id] = run
            return run

    async def get(self, run_id: str) -> ParallelRunState:
        """Return a run by ID."""

        async with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise ParallelRunNotFoundError(f"parallel run does not exist: {run_id}")
            return run

    async def mutate(
        self,
        run_id: str,
        mutator: Callable[[ParallelRunState], None],
    ) -> ParallelRunState:
        """Apply a synchronous state mutation under the store lock."""

        async with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise ParallelRunNotFoundError(f"parallel run does not exist: {run_id}")
            mutator(run)
            return run


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(tz=UTC)


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
