from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio

from paynkolay_pos.api.app import create_app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client


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
async def test_payment_form_accepts_valid_browser_payload(client: httpx.AsyncClient) -> None:
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
    assert payload["status"] == "created"
    assert payload["amount"] == "100.00"
    assert payload["requires_3ds"] is True
    assert payload["masked_pan"] == "411111******1111"
    assert "4111111111111111" not in response.text
    assert "123" not in response.text


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
            "requires_3ds": False,
            "installment_count": 2,
        },
    )
    assert create_response.status_code == 202

    response = await client.get("/api/payments/order-web-1001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["order_id"] == "order-web-1001"
    assert payload["status"] == "created"
    assert payload["amount"] == "250.50"
    assert payload["masked_pan"] == "411111******1111"
    assert payload["card_holder"] == "PAYNKOLAY TEST"
    assert payload["requires_3ds"] is False
    assert payload["installment_count"] == 2
    assert "4111111111111111" not in response.text
    assert "123" not in response.text


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
