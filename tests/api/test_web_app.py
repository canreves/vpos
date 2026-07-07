from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from paynkolay_pos.api.app import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.mark.api
def test_health_check_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "paynkolay-pos-web",
        "version": "0.1.0",
    }


@pytest.mark.api
def test_root_renders_payment_screen(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'id="payment-form"' in response.text


@pytest.mark.api
def test_config_route_exposes_safe_defaults_without_runtime_settings(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PAYNKOLAY_CONFIG_FILE", raising=False)

    response = client.get("/api/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime_configured"] is False
    assert payload["supported_currencies"] == ["TRY", "USD", "EUR"]
    assert payload["supported_card_brands"] == ["visa", "mastercard", "troy"]
    assert payload["payment_channels"] == ["e_commerce", "moto"]
    assert payload["card_aliases"] == []


@pytest.mark.api
def test_payment_form_accepts_valid_browser_payload(client: TestClient) -> None:
    response = client.post(
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
    assert "4111111111111111" not in response.text
    assert "123" not in response.text


@pytest.mark.api
def test_payment_form_rejects_non_numeric_card_number(client: TestClient) -> None:
    response = client.post(
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

