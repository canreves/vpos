from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio

from paynkolay_pos.api.app import create_app
from paynkolay_pos.api.dependencies import (
    get_external_payment_logger,
    get_payment_initializer,
)
from paynkolay_pos.api.payment_initializer import (
    PaymentInitializationOutcome,
    PaymentProviderInitializationError,
)
from paynkolay_pos.api.schemas import PaymentFormRequest
from paynkolay_pos.models import (
    Currency,
    PaymentCardInput,
    PaymentInitializeRequest,
    PaynkolayPaymentResult,
    PaynkolayThreeDSInitializeResult,
)
from paynkolay_pos.reporting import PaymentLogEvent


@pytest_asyncio.fixture
async def fake_initializer() -> AsyncIterator[FakePaymentInitializer]:
    yield FakePaymentInitializer()


@pytest_asyncio.fixture
async def fake_logger() -> AsyncIterator[FakeExternalPaymentLogger]:
    yield FakeExternalPaymentLogger()


@pytest_asyncio.fixture
async def client(
    fake_initializer: FakePaymentInitializer,
    fake_logger: FakeExternalPaymentLogger,
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_payment_initializer] = lambda: fake_initializer
    app.dependency_overrides[get_external_payment_logger] = lambda: fake_logger
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client


class FakeExternalPaymentLogger:
    def __init__(self) -> None:
        self.events: list[PaymentLogEvent] = []

    async def log(self, event: PaymentLogEvent) -> None:
        self.events.append(event)


class FakePaymentInitializer:
    def __init__(
        self,
        *,
        provider_result: PaynkolayThreeDSInitializeResult | PaynkolayPaymentResult | None = None,
        fails: bool = False,
    ) -> None:
        self.provider_result = provider_result or PaynkolayThreeDSInitializeResult.model_validate(
            {"BANK_REQUEST_MESSAGE": "<form>3DS challenge</form>"}
        )
        self.fails = fails
        self.calls: list[tuple[str, str]] = []

    async def initialize(
        self,
        request: PaymentFormRequest,
        *,
        order_id: str,
        card_holder_ip: str,
    ) -> PaymentInitializationOutcome:
        self.calls.append((order_id, card_holder_ip))
        if self.fails:
            raise PaymentProviderInitializationError("provider payment initialization failed")
        return PaymentInitializationOutcome(
            payment_request=_payment_request(request, order_id=order_id),
            provider_result=self.provider_result,
            success_url="https://merchant.example.test/payments/result/success",
            fail_url="https://merchant.example.test/payments/result/fail",
        )


def _payment_request(
    request: PaymentFormRequest,
    *,
    order_id: str,
) -> PaymentInitializeRequest:
    return PaymentInitializeRequest(
        merchant_id="merchant-web",
        terminal_id="terminal-web",
        order_id=order_id,
        amount=request.amount,
        currency=request.currency,
        callback_url="https://merchant.example.test/callbacks/paynkolay",
        card=PaymentCardInput(
            brand=request.card_brand,
            pan=request.card_number,
            expiry_month=request.expiry_month,
            expiry_year=request.expiry_year,
            cvv=request.cvv,
            card_holder=request.card_holder,
        ),
        requires_3ds=request.requires_3ds,
        installment_count=request.installment_count,
        correlation_id=f"web-{order_id}",
    )


@pytest.mark.api
@pytest.mark.asyncio
async def test_health_check_returns_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "paynkolay-pos-web",
        "version": "0.1.0",
    }


@pytest.mark.api
@pytest.mark.asyncio
async def test_root_renders_payment_screen(client: httpx.AsyncClient) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'id="payment-form"' in response.text


@pytest.mark.api
@pytest.mark.asyncio
async def test_config_route_exposes_safe_defaults_without_runtime_settings(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PAYNKOLAY_CONFIG_FILE", raising=False)

    response = await client.get("/api/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime_configured"] is False
    assert payload["supported_currencies"] == ["TRY", "USD", "EUR"]
    assert payload["supported_card_brands"] == ["visa", "mastercard", "troy"]
    assert payload["payment_channels"] == ["e_commerce", "moto"]
    assert payload["card_aliases"] == []


@pytest.mark.api
@pytest.mark.asyncio
async def test_payment_form_initializes_provider_and_returns_3ds_state(
    client: httpx.AsyncClient,
    fake_initializer: FakePaymentInitializer,
    fake_logger: FakeExternalPaymentLogger,
) -> None:
    response = await client.post(
        "/api/payments",
        json={
            "amount": "100.00",
            "currency": "TRY",
            "card_number": "4111111111111111",
            "card_holder": "PAYNKOLAY TEST",
            "expiry_month": 12,
            "expiry_year": 2030,
            "cvv": "123",
            "requires_3ds": True,
            "installment_count": 1,
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["order_id"].startswith("web-")
    assert payload["status"] == "pending_3ds"
    assert payload["amount"] == "100.00"
    assert payload["requires_3ds"] is True
    assert payload["masked_pan"] == "411111******1111"
    assert payload["three_ds"] == {"render_url": f"/payments/{payload['order_id']}/three-ds"}
    assert fake_initializer.calls == [(payload["order_id"], "127.0.0.1")]
    assert "4111111111111111" not in str([event.model_dump() for event in fake_logger.events])
    assert "123" not in str([event.model_dump() for event in fake_logger.events])
    assert "4111111111111111" not in response.text
    assert "123" not in response.text

    three_ds_response = await client.get(payload["three_ds"]["render_url"])

    assert three_ds_response.status_code == 200
    assert "<form>3DS challenge</form>" in three_ds_response.text
    assert [event.event for event in fake_logger.events] == [
        "payment_initialized",
        "three_ds_required",
        "three_ds_rendered",
    ]


@pytest.mark.api
@pytest.mark.asyncio
async def test_payment_lookup_returns_stored_session(client: httpx.AsyncClient) -> None:
    create_response = await client.post(
        "/api/payments",
        json={
            "order_id": "order-web-1001",
            "amount": "250.50",
            "currency": "TRY",
            "card_number": "4111111111111111",
            "card_holder": "PAYNKOLAY TEST",
            "expiry_month": 12,
            "expiry_year": 2030,
            "cvv": "123",
            "requires_3ds": True,
            "installment_count": 2,
        },
    )
    assert create_response.status_code == 202

    response = await client.get("/api/payments/order-web-1001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["order_id"] == "order-web-1001"
    assert payload["status"] == "pending_3ds"
    assert payload["amount"] == "250.50"
    assert payload["masked_pan"] == "411111******1111"
    assert payload["card_holder"] == "PAYNKOLAY TEST"
    assert payload["requires_3ds"] is True
    assert payload["installment_count"] == 2
    assert payload["links"]["three_ds"] == "/payments/order-web-1001/three-ds"
    assert "4111111111111111" not in response.text
    assert "123" not in response.text


@pytest.mark.api
@pytest.mark.asyncio
async def test_payment_form_records_final_provider_result() -> None:
    final_result = PaynkolayPaymentResult.model_validate(
        {
            "RESPONSE_CODE": "2",
            "RESPONSE_DATA": "Islem Basarili",
            "USE_3D": "false",
            "RND": "rnd-1001",
            "MERCHANT_NO": "merchant-web",
            "AUTH_CODE": "AUTH1001",
            "REFERENCE_CODE": "ref-1001",
            "CLIENT_REFERENCE_CODE": "order-web-final",
            "TIMESTAMP": "2026-07-07T12:00:00+00:00",
            "TRANSACTION_AMOUNT": "100.00",
            "AUTHORIZATION_AMOUNT": "100.00",
            "INSTALLMENT": 1,
            "CURRENCY_CODE": Currency.TRY,
            "hashDataV2": "hash",
        }
    )
    app = create_app()
    app.dependency_overrides[get_payment_initializer] = lambda: FakePaymentInitializer(
        provider_result=final_result
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/payments",
            json={
                "order_id": "order-web-final",
                "amount": "100.00",
                "currency": "TRY",
                "card_number": "4111111111111111",
                "card_holder": "PAYNKOLAY TEST",
                "expiry_month": 12,
                "expiry_year": 2030,
                "cvv": "123",
                "requires_3ds": False,
                "installment_count": 1,
            },
        )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["provider_transaction_id"] == "ref-1001"
    assert payload["three_ds"] is None


@pytest.mark.api
@pytest.mark.asyncio
async def test_payment_form_marks_session_failed_when_provider_initializer_fails() -> None:
    app = create_app()
    app.dependency_overrides[get_payment_initializer] = lambda: FakePaymentInitializer(fails=True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/payments",
            json={
                "order_id": "order-provider-fails",
                "amount": "100.00",
                "currency": "TRY",
                "card_number": "4111111111111111",
                "card_holder": "PAYNKOLAY TEST",
                "expiry_month": 12,
                "expiry_year": 2030,
                "cvv": "123",
                "requires_3ds": True,
                "installment_count": 1,
            },
        )
        lookup_response = await client.get("/api/payments/order-provider-fails")

    assert response.status_code == 502
    assert lookup_response.status_code == 200
    assert lookup_response.json()["status"] == "failed"


@pytest.mark.api
@pytest.mark.asyncio
async def test_payment_form_rejects_duplicate_order_id(client: httpx.AsyncClient) -> None:
    payload = {
        "order_id": "order-web-duplicate",
        "amount": "100.00",
        "currency": "TRY",
        "card_number": "4111111111111111",
        "card_holder": "PAYNKOLAY TEST",
        "expiry_month": 12,
        "expiry_year": 2030,
        "cvv": "123",
        "requires_3ds": True,
        "installment_count": 1,
    }

    first_response = await client.post("/api/payments", json=payload)
    duplicate_response = await client.post("/api/payments", json=payload)

    assert first_response.status_code == 202
    assert duplicate_response.status_code == 409


@pytest.mark.api
@pytest.mark.asyncio
async def test_payment_lookup_returns_404_for_unknown_order(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/payments/missing-order")

    assert response.status_code == 404


@pytest.mark.api
@pytest.mark.asyncio
async def test_payment_form_returns_503_without_runtime_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PAYNKOLAY_CONFIG_FILE", raising=False)
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/payments",
            json={
                "amount": "100.00",
                "currency": "TRY",
                "card_number": "4111111111111111",
                "card_holder": "PAYNKOLAY TEST",
                "expiry_month": 12,
                "expiry_year": 2030,
                "cvv": "123",
                "requires_3ds": True,
                "installment_count": 1,
            },
        )

    assert response.status_code == 503


@pytest.mark.api
@pytest.mark.asyncio
async def test_payment_form_rejects_non_numeric_card_number(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/payments",
        json={
            "amount": "100.00",
            "currency": "TRY",
            "card_number": "41111111111x1111",
            "card_holder": "PAYNKOLAY TEST",
            "expiry_month": 12,
            "expiry_year": 2030,
            "cvv": "123",
            "requires_3ds": True,
            "installment_count": 1,
        },
    )

    assert response.status_code == 422
