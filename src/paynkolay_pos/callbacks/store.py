"""In-memory callback storage and matching for asynchronous payment tests."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from time import monotonic

from paynkolay_pos.models import CallbackPayload

CallbackMatcher = Callable[[CallbackPayload], bool]


class CallbackStore:
    """Worker-local callback store used by tests before a real receiver exists."""

    def __init__(
        self,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._callbacks_by_order_id: defaultdict[str, list[CallbackPayload]] = defaultdict(list)
        self._sleep = sleep
        self._clock = clock

    def add(self, callback: CallbackPayload) -> None:
        """Store a provider callback under its merchant order ID."""

        self._callbacks_by_order_id[callback.order_id].append(callback)

    def callbacks_for(self, order_id: str) -> tuple[CallbackPayload, ...]:
        """Return all callbacks currently stored for an order ID."""

        return tuple(self._callbacks_by_order_id.get(order_id, ()))

    def latest_for(self, order_id: str) -> CallbackPayload | None:
        """Return the latest callback stored for an order ID, if one exists."""

        callbacks = self._callbacks_by_order_id.get(order_id)
        if not callbacks:
            return None
        return callbacks[-1]

    async def wait_for(
        self,
        order_id: str,
        *,
        matcher: CallbackMatcher | None = None,
        timeout_seconds: float = 30.0,
        poll_interval_seconds: float = 0.5,
    ) -> CallbackPayload:
        """Poll the store until a callback for an order ID satisfies the matcher."""

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than zero")

        deadline = self._clock() + timeout_seconds

        while self._clock() <= deadline:
            for callback in self.callbacks_for(order_id):
                if matcher is None or matcher(callback):
                    return callback
            await self._sleep(poll_interval_seconds)

        known_order_ids = ", ".join(sorted(self._callbacks_by_order_id)) or "none"
        stored_count = len(self.callbacks_for(order_id))
        raise TimeoutError(
            f"callback for order_id={order_id!r} was not received within "
            f"{timeout_seconds:.2f}s; stored callbacks for order_id: {stored_count}; "
            f"known order IDs: {known_order_ids}"
        )
