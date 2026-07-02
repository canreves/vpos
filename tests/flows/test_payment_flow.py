from __future__ import annotations

import pytest
from pydantic import SecretStr

from paynkolay_pos.callbacks import (
    CallbackSignatureVerificationError,
    CallbackStore,
)
from paynkolay_pos.flows import PaymentFlow, PaymentFlowCallbackMismatchError
from paynkolay_pos.models import (
    PaymentInitializeRequest,
    PaymentInitializeResponse,
    PaymentStatus,
    TransactionStatusResponse,
)
from paynkolay_pos.testing import (
    payment_initialize_request,
    signed_callback_payload_model,
    transaction_status_response,
)


class FakePaymentClient:
    def __init__(
        self,
        response: PaymentInitializeResponse,
        statuses: list[TransactionStatusResponse] | None = None,
    ) -> None:
        self.response = response
        self.statuses = statuses or []
        self.seen_request: PaymentInitializeRequest | None = None
        self.seen_order_ids: list[str] = []

    async def initialize_payment(
        self,
        request: PaymentInitializeRequest,
    ) -> PaymentInitializeResponse:
        self.seen_request = request
        return self.response

    async def get_transaction_status(self, order_id: str) -> TransactionStatusResponse:
        self.seen_order_ids.append(order_id)
        if not self.statuses:
            raise AssertionError("fake client has no status responses left")
        return self.statuses.pop(0)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.mark.api
@pytest.mark.asyncio
async def test_payment_flow_initializes_payment_through_client() -> None:
    provider_response = PaymentInitializeResponse.model_validate(
        {
            "order_id": "order-1001",
            "provider_transaction_id": "txn-1001",
            "status": "pending_3ds",
            "amount": "100.00",
            "currency": "TRY",
            "redirect_url": "https://acs.example.test/challenge/order-1001",
        }
    )
    client = FakePaymentClient(provider_response)
    request = payment_initialize_request()

    response = await PaymentFlow(client).initialize(request)

    assert response is provider_response
    assert response.status is PaymentStatus.PENDING_3DS
    assert response.redirect_url == "https://acs.example.test/challenge/order-1001"
    assert client.seen_request is request


@pytest.mark.api
@pytest.mark.asyncio
async def test_payment_flow_waits_until_transaction_reaches_final_status() -> None:
    clock = FakeClock()
    client = FakePaymentClient(
        PaymentInitializeResponse.model_validate(
            {
                "order_id": "order-1001",
                "status": "created",
                "amount": "100.00",
                "currency": "TRY",
            }
        ),
        statuses=[
            transaction_status_response(PaymentStatus.PENDING_3DS),
            transaction_status_response(PaymentStatus.AUTHENTICATED),
            transaction_status_response(PaymentStatus.CAPTURED),
        ],
    )

    response = await PaymentFlow(client, sleep=clock.sleep, clock=clock).wait_for_final_status(
        "order-1001",
        timeout_seconds=10.0,
        poll_interval_seconds=0.5,
    )

    assert response.status is PaymentStatus.CAPTURED
    assert response.authorization_code == "auth-1001"
    assert client.seen_order_ids == ["order-1001", "order-1001", "order-1001"]
    assert clock.now == 1.0


@pytest.mark.callback
@pytest.mark.asyncio
async def test_payment_flow_waits_for_verified_matching_callback() -> None:
    request = payment_initialize_request()
    final_status = transaction_status_response(PaymentStatus.CAPTURED)
    callback = signed_callback_payload_model()
    callback_store = CallbackStore()
    callback_store.add(callback)
    client = FakePaymentClient(
        PaymentInitializeResponse.model_validate(
            {
                "order_id": "order-1001",
                "status": "created",
                "amount": "100.00",
                "currency": "TRY",
            }
        )
    )

    confirmed_callback = await PaymentFlow(client).wait_for_verified_callback(
        request,
        final_status,
        callback_store=callback_store,
        secret_key=SecretStr("callback-secret"),
    )

    assert confirmed_callback is callback


@pytest.mark.callback
@pytest.mark.negative
@pytest.mark.asyncio
async def test_payment_flow_rejects_callback_with_invalid_signature() -> None:
    request = payment_initialize_request()
    final_status = transaction_status_response(PaymentStatus.CAPTURED)
    callback = signed_callback_payload_model(secret_key="different-secret")
    callback_store = CallbackStore()
    callback_store.add(callback)
    client = FakePaymentClient(
        PaymentInitializeResponse.model_validate(
            {
                "order_id": "order-1001",
                "status": "created",
                "amount": "100.00",
                "currency": "TRY",
            }
        )
    )

    with pytest.raises(CallbackSignatureVerificationError):
        await PaymentFlow(client).wait_for_verified_callback(
            request,
            final_status,
            callback_store=callback_store,
            secret_key=SecretStr("callback-secret"),
        )


@pytest.mark.callback
@pytest.mark.negative
@pytest.mark.asyncio
async def test_payment_flow_rejects_verified_callback_that_disagrees_with_payment() -> None:
    request = payment_initialize_request()
    final_status = transaction_status_response(PaymentStatus.CAPTURED)
    callback = signed_callback_payload_model(amount="99.00")
    callback_store = CallbackStore()
    callback_store.add(callback)
    client = FakePaymentClient(
        PaymentInitializeResponse.model_validate(
            {
                "order_id": "order-1001",
                "status": "created",
                "amount": "100.00",
                "currency": "TRY",
            }
        )
    )

    with pytest.raises(
        PaymentFlowCallbackMismatchError,
        match="callback amount does not match payment evidence",
    ):
        await PaymentFlow(client).wait_for_verified_callback(
            request,
            final_status,
            callback_store=callback_store,
            secret_key=SecretStr("callback-secret"),
        )


@pytest.mark.negative
@pytest.mark.asyncio
async def test_payment_flow_times_out_when_transaction_never_reaches_final_status() -> None:
    clock = FakeClock()
    client = FakePaymentClient(
        PaymentInitializeResponse.model_validate(
            {
                "order_id": "order-1001",
                "status": "created",
                "amount": "100.00",
                "currency": "TRY",
            }
        ),
        statuses=[
            transaction_status_response(PaymentStatus.PENDING_3DS),
            transaction_status_response(PaymentStatus.AUTHENTICATED),
            transaction_status_response(PaymentStatus.AUTHENTICATED),
        ],
    )

    with pytest.raises(
        TimeoutError,
        match="transaction 'order-1001' did not reach a final status within 1.00s",
    ):
        await PaymentFlow(client, sleep=clock.sleep, clock=clock).wait_for_final_status(
            "order-1001",
            timeout_seconds=1.0,
            poll_interval_seconds=0.5,
        )


@pytest.mark.negative
@pytest.mark.asyncio
async def test_payment_flow_rejects_invalid_polling_timing() -> None:
    client = FakePaymentClient(
        PaymentInitializeResponse.model_validate(
            {
                "order_id": "order-1001",
                "status": "created",
                "amount": "100.00",
                "currency": "TRY",
            }
        )
    )
    flow = PaymentFlow(client)

    with pytest.raises(ValueError, match="timeout_seconds must be greater than zero"):
        await flow.wait_for_final_status("order-1001", timeout_seconds=0)

    with pytest.raises(ValueError, match="poll_interval_seconds must be greater than zero"):
        await flow.wait_for_final_status("order-1001", poll_interval_seconds=0)
