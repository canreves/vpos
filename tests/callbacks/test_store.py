from __future__ import annotations

import pytest

from paynkolay_pos.callbacks import CallbackStore
from paynkolay_pos.models import CallbackPayload, PaymentStatus


def callback_payload(
    *,
    order_id: str = "order-1001",
    status: str = "captured",
    signature: str = "a" * 64,
) -> CallbackPayload:
    payload: dict[str, object] = {
        "order_id": order_id,
        "provider_transaction_id": f"txn-{order_id}",
        "status": status,
        "amount": "100.00",
        "currency": "TRY",
        "received_at": "2026-07-02T12:00:00+03:00",
        "signature": signature,
    }
    if status in {"authorized", "captured"}:
        payload["authorization_code"] = f"auth-{order_id}"
    if status == "failed":
        payload["failure_code"] = "issuer_declined"
    return CallbackPayload.model_validate(payload)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.mark.callback
def test_callback_store_keeps_callbacks_grouped_by_order_id() -> None:
    store = CallbackStore()
    first_callback = callback_payload(order_id="order-1001", status="authorized")
    second_callback = callback_payload(order_id="order-1001", status="captured")
    other_callback = callback_payload(order_id="order-2002", status="failed")

    store.add(first_callback)
    store.add(other_callback)
    store.add(second_callback)

    assert store.callbacks_for("order-1001") == (first_callback, second_callback)
    assert store.latest_for("order-1001") is second_callback
    assert store.callbacks_for("missing-order") == ()
    assert store.latest_for("missing-order") is None


@pytest.mark.callback
@pytest.mark.asyncio
async def test_callback_store_waits_for_matching_callback() -> None:
    clock = FakeClock()
    pending_callback = callback_payload(status="authorized")
    final_callback = callback_payload(status="captured", signature="b" * 64)

    async def add_final_callback_after_first_poll(seconds: float) -> None:
        await clock.sleep(seconds)
        store.add(final_callback)

    store = CallbackStore(sleep=add_final_callback_after_first_poll, clock=clock)
    store.add(pending_callback)

    callback = await store.wait_for(
        "order-1001",
        matcher=lambda stored_callback: stored_callback.status is PaymentStatus.CAPTURED,
        timeout_seconds=2.0,
        poll_interval_seconds=0.5,
    )

    assert callback is final_callback
    assert clock.now == 0.5


@pytest.mark.callback
@pytest.mark.negative
@pytest.mark.asyncio
async def test_callback_store_times_out_with_diagnostics() -> None:
    clock = FakeClock()
    store = CallbackStore(sleep=clock.sleep, clock=clock)
    store.add(callback_payload(order_id="order-2002"))

    with pytest.raises(
        TimeoutError,
        match=(
            "callback for order_id='order-1001' was not received within 1.00s; "
            "stored callbacks for order_id: 0; known order IDs: order-2002"
        ),
    ):
        await store.wait_for(
            "order-1001",
            timeout_seconds=1.0,
            poll_interval_seconds=0.5,
        )


@pytest.mark.callback
@pytest.mark.negative
@pytest.mark.asyncio
async def test_callback_store_rejects_invalid_polling_timing() -> None:
    store = CallbackStore()

    with pytest.raises(ValueError, match="timeout_seconds must be greater than zero"):
        await store.wait_for("order-1001", timeout_seconds=0)

    with pytest.raises(ValueError, match="poll_interval_seconds must be greater than zero"):
        await store.wait_for("order-1001", poll_interval_seconds=0)
