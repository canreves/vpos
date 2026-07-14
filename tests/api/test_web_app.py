from __future__ import annotations

import asyncio
import json
import subprocess
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

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
    PaymentProviderStatusVerificationError,
)
from paynkolay_pos.api.routes import reports
from paynkolay_pos.api.schemas import PaymentFormRequest
from paynkolay_pos.config import build_private_runtime_config_payload
from paynkolay_pos.models import (
    Currency,
    PaymentCardInput,
    PaymentInitializeRequest,
    PaymentStatus,
    PaynkolayPaymentResult,
    PaynkolayThreeDSInitializeResult,
    TransactionStatusResponse,
)
from paynkolay_pos.reporting import PaymentLogEvent
from paynkolay_pos.scenarios import build_private_scenario_catalog_payload


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
        outcomes: list[
            PaynkolayThreeDSInitializeResult | PaynkolayPaymentResult | BaseException
        ] | None = None,
        payment_list_status: TransactionStatusResponse | None = None,
        fails: bool = False,
        status_fails: bool = False,
    ) -> None:
        self.provider_result = provider_result or PaynkolayThreeDSInitializeResult.model_validate(
            {"BANK_REQUEST_MESSAGE": "<form>3DS challenge</form>"}
        )
        self.outcomes = outcomes or []
        self.payment_list_status = payment_list_status
        self.fails = fails
        self.status_fails = status_fails
        self.calls: list[tuple[str, str]] = []
        self.requests: list[PaymentFormRequest] = []
        self.status_calls: list[str] = []

    async def initialize(
        self,
        request: PaymentFormRequest,
        *,
        order_id: str,
        card_holder_ip: str,
    ) -> PaymentInitializationOutcome:
        self.calls.append((order_id, card_holder_ip))
        self.requests.append(request)
        if self.fails:
            raise PaymentProviderInitializationError("provider payment initialization failed")
        provider_result = self.provider_result
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            provider_result = outcome
        return PaymentInitializationOutcome(
            payment_request=_payment_request(request, order_id=order_id),
            provider_result=provider_result,
            success_url="https://merchant.example.test/payments/result/success",
            fail_url="https://merchant.example.test/payments/result/fail",
        )

    async def verify_transaction_status(
        self,
        order_id: str,
        *,
        currency: Currency,
    ) -> TransactionStatusResponse:
        self.status_calls.append(order_id)
        if self.status_fails:
            raise PaymentProviderStatusVerificationError(
                "provider payment status verification failed"
            )
        return self.payment_list_status or TransactionStatusResponse(
            order_id=order_id,
            provider_transaction_id="list-ref-1001",
            status=PaymentStatus.CAPTURED,
            amount=Decimal("100.00"),
            currency=currency,
            updated_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
            authorization_code="LISTAUTH",
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


def _payment_result(
    *,
    response_code: str,
    response_data: str,
) -> PaynkolayPaymentResult:
    return PaynkolayPaymentResult.model_validate(
        {
            "RESPONSE_CODE": response_code,
            "RESPONSE_DATA": response_data,
            "USE_3D": "false",
            "RND": "rnd-parallel",
            "MERCHANT_NO": "merchant-web",
            "AUTH_CODE": "AUTHPAR",
            "REFERENCE_CODE": "ref-parallel",
            "CLIENT_REFERENCE_CODE": "parallel-order",
            "TIMESTAMP": "2026-07-07T12:00:00+00:00",
            "TRANSACTION_AMOUNT": "100.00",
            "AUTHORIZATION_AMOUNT": "100.00",
            "INSTALLMENT": 1,
            "CURRENCY_CODE": Currency.TRY,
            "hashDataV2": "hash",
        }
    )


def _runtime_card(
    *,
    alias: str,
    pan: str,
    requires_3ds: bool,
    expected_otp: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "alias": alias,
        "brand": "visa",
        "pan": pan,
        "expiry_month": 12,
        "expiry_year": 2030,
        "cvv": "123",
        "requires_3ds": requires_3ds,
    }
    if expected_otp is not None:
        payload["expected_otp"] = expected_otp
    return payload


def _write_parallel_runtime_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cards: list[dict[str, object]],
) -> Path:
    config_path = tmp_path / "parallel-settings.json"
    config_payload = build_private_runtime_config_payload(card_count=10)
    environments = cast(dict[str, Any], config_payload["environments"])
    dev = cast(dict[str, Any], environments["dev"])
    dev["cards"] = cards
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")
    monkeypatch.setenv("PAYNKOLAY_CONFIG_FILE", str(config_path))
    monkeypatch.setenv("PAYNKOLAY_ENV", "dev")
    return config_path


async def _wait_parallel_run(
    client: httpx.AsyncClient,
    run_id: str,
) -> dict[str, Any]:
    for _ in range(10):
        response = await client.get(f"/api/parallel-runs/{run_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] != "running":
            return cast(dict[str, Any], payload)
        await asyncio.sleep(0.01)
    raise AssertionError(f"parallel run did not finish: {run_id}")


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
    assert 'rel="icon" href="/static/favicon.svg"' in response.text
    assert 'id="card-list-button"' in response.text
    assert 'id="card-list-body"' in response.text
    assert 'id="card-list-search"' in response.text
    assert 'id="card-list-flow-filter"' in response.text
    assert 'id="card-add-toggle"' in response.text
    assert 'id="card-add-form"' in response.text
    assert 'id="installment-status"' in response.text
    assert 'id="result-payment-list-status"' in response.text


@pytest.mark.api
@pytest.mark.asyncio
async def test_reports_page_renders_dynamic_report_screen(client: httpx.AsyncClient) -> None:
    response = await client.get("/reports")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'id="report-status"' in response.text
    assert 'id="history-status"' in response.text
    assert 'id="credential-run-button"' in response.text
    assert "make credential-scenario-report" in response.text
    assert "/static/js/reports.js" in response.text


@pytest.mark.api
@pytest.mark.asyncio
async def test_parallel_page_renders_parallel_run_screen(client: httpx.AsyncClient) -> None:
    response = await client.get("/parallel")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'class="nav-link active" href="/parallel"' in response.text
    assert 'id="parallel-run-button"' in response.text
    assert 'id="parallel-selection-body"' in response.text
    assert 'id="parallel-results-body"' in response.text
    assert "/static/js/parallel-runs.js" in response.text


@pytest.mark.api
@pytest.mark.asyncio
async def test_favicon_redirects_to_static_svg(client: httpx.AsyncClient) -> None:
    response = await client.get("/favicon.ico", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/static/favicon.svg"


@pytest.mark.api
@pytest.mark.asyncio
async def test_settings_page_renders_dynamic_config_screen(client: httpx.AsyncClient) -> None:
    response = await client.get("/settings")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'id="runtime-status"' in response.text
    assert 'id="settings-cards"' in response.text
    assert 'id="coverage-3ds"' in response.text
    assert "make credential-inputs" in response.text
    assert "/static/js/settings.js" in response.text


@pytest.mark.api
@pytest.mark.asyncio
async def test_result_page_renders_dynamic_lookup_screen(client: httpx.AsyncClient) -> None:
    response = await client.get("/result?order_id=order-web-1001")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'id="result-lookup-form"' in response.text
    assert 'id="lookup-order-id"' in response.text
    assert 'id="result-payment-list-status"' in response.text
    assert 'class="nav-link active" href="/"' in response.text
    assert "/static/js/result.js" in response.text


@pytest.mark.api
@pytest.mark.asyncio
async def test_latest_report_returns_unavailable_when_report_is_missing(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "missing-report"
    monkeypatch.setenv("PAYNKOLAY_ALLURE_REPORT_DIR", str(report_dir))

    response = await client.get("/api/reports/latest")

    assert response.status_code == 200
    assert response.json() == {
        "available": False,
        "report_path": str(report_dir),
        "entrypoint": None,
        "message": "Allure HTML report has not been generated yet.",
    }


@pytest.mark.api
@pytest.mark.asyncio
async def test_latest_report_returns_available_when_index_exists(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "allure-report"
    report_dir.mkdir()
    entrypoint = report_dir / "index.html"
    entrypoint.write_text("<!doctype html><title>Allure</title>", encoding="utf-8")
    monkeypatch.setenv("PAYNKOLAY_ALLURE_REPORT_DIR", str(report_dir))

    response = await client.get("/api/reports/latest")

    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "report_path": str(report_dir),
        "entrypoint": str(entrypoint),
        "message": "Allure HTML report is available.",
    }


@pytest.mark.api
@pytest.mark.asyncio
async def test_report_history_returns_unavailable_when_results_are_missing(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "missing-results"
    monkeypatch.setenv("PAYNKOLAY_ALLURE_RESULTS_DIR", str(results_dir))

    response = await client.get("/api/reports/history")

    assert response.status_code == 200
    assert response.json() == {
        "available": False,
        "results_path": str(results_dir),
        "latest": None,
        "message": "Allure results have not been generated yet.",
    }


@pytest.mark.api
@pytest.mark.asyncio
async def test_report_history_summarizes_latest_allure_results(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "allure-results"
    results_dir.mkdir()
    monkeypatch.setenv("PAYNKOLAY_ALLURE_RESULTS_DIR", str(results_dir))
    (results_dir / "passed-result.json").write_text(
        json.dumps(
            {
                "name": "test_authorized_payment",
                "status": "passed",
                "start": 1783510684000,
                "stop": 1783510684050,
                "labels": [{"name": "suite", "value": "test_payments"}],
            }
        ),
        encoding="utf-8",
    )
    (results_dir / "failed-result.json").write_text(
        json.dumps(
            {
                "name": "test_invalid_cvv",
                "status": "failed",
                "start": 1783510684100,
                "stop": 1783510684200,
                "labels": [{"name": "suite", "value": "test_payments"}],
            }
        ),
        encoding="utf-8",
    )

    response = await client.get("/api/reports/history")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["results_path"] == str(results_dir)
    assert payload["latest"]["total"] == 2
    assert payload["latest"]["passed"] == 1
    assert payload["latest"]["failed"] == 1
    assert payload["latest"]["duration_ms"] == 200
    assert payload["latest"]["recent_tests"][0]["name"] == "test_invalid_cvv"
    assert payload["latest"]["recent_tests"][0]["duration_ms"] == 100


@pytest.mark.api
@pytest.mark.asyncio
async def test_credential_report_run_status_starts_idle(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/reports/credential-run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "idle"
    assert payload["command"] == ["make", "credential-scenario-report"]
    assert payload["exit_code"] is None


@pytest.mark.api
@pytest.mark.asyncio
async def test_credential_report_run_executes_fixed_command(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run_command(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="77 passed", stderr="")

    monkeypatch.setattr(reports, "_run_command", fake_run_command)

    response = await client.post("/api/reports/credential-run")

    assert response.status_code == 202
    assert response.json()["status"] == "running"
    status_response = await client.get("/api/reports/credential-run")
    payload = status_response.json()
    assert calls == [("make", "credential-scenario-report")]
    assert payload["status"] == "passed"
    assert payload["exit_code"] == 0
    assert payload["output_tail"] == "77 passed"


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
async def test_cards_route_requires_runtime_settings(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PAYNKOLAY_CONFIG_FILE", raising=False)

    response = await client.get("/api/cards")

    assert response.status_code == 503
    assert "runtime payment configuration is unavailable" in response.json()["detail"]


@pytest.mark.api
@pytest.mark.asyncio
async def test_cards_route_returns_form_fill_test_cards(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "settings.json"
    config_payload = build_private_runtime_config_payload(card_count=10)
    environments = cast(dict[str, Any], config_payload["environments"])
    dev = cast(dict[str, Any], environments["dev"])
    cards = cast(list[dict[str, Any]], dev["cards"])
    cards[0].update(
        {
            "alias": "ui_card_3ds",
            "brand": "visa",
            "pan": "4111111111111111",
            "expiry_month": 1,
            "expiry_year": 2030,
            "cvv": "123",
            "requires_3ds": True,
            "expected_otp": "123456",
        }
    )
    cards[1].update(
        {
            "alias": "ui_card_moto",
            "brand": "mastercard",
            "pan": "5555555555554444",
            "expiry_month": 12,
            "expiry_year": 2031,
            "cvv": "999",
            "requires_3ds": False,
            "expected_otp": None,
        }
    )
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")
    monkeypatch.setenv("PAYNKOLAY_CONFIG_FILE", str(config_path))

    response = await client.get("/api/cards")

    assert response.status_code == 200
    payload = response.json()
    assert payload["environment"] == "dev"
    assert payload["cards"][0] == {
        "alias": "ui_card_3ds",
        "brand": "visa",
        "flow_type": "secure",
        "card_number": "4111111111111111",
        "cvv": "123",
        "expiry_month": 1,
        "expiry_year": 2030,
        "card_holder": "PAYNKOLAY TEST",
        "requires_3ds": True,
        "has_expected_otp": True,
    }
    assert payload["cards"][1]["alias"] == "ui_card_moto"
    assert payload["cards"][1]["flow_type"] == "moto"
    assert payload["cards"][1]["requires_3ds"] is False
    assert payload["cards"][1]["has_expected_otp"] is False


@pytest.mark.api
@pytest.mark.asyncio
async def test_cards_route_appends_new_moto_card_to_runtime_config(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "settings.json"
    config_payload = build_private_runtime_config_payload(card_count=10)
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")
    monkeypatch.setenv("PAYNKOLAY_CONFIG_FILE", str(config_path))

    response = await client.post(
        "/api/cards",
        json={
            "alias": "manual_moto_card",
            "brand": "visa",
            "card_number": "4111111111111234",
            "expiry_month": 10,
            "expiry_year": 2030,
            "cvv": "321",
            "flow_type": "moto",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["alias"] == "manual_moto_card"
    assert payload["flow_type"] == "moto"
    updated = json.loads(config_path.read_text(encoding="utf-8"))
    cards = updated["environments"]["dev"]["cards"]
    assert cards[-1] == {
        "alias": "manual_moto_card",
        "brand": "visa",
        "pan": "4111111111111234",
        "expiry_month": 10,
        "expiry_year": 2030,
        "cvv": "321",
        "requires_3ds": False,
    }


@pytest.mark.api
@pytest.mark.asyncio
async def test_cards_route_appends_new_3ds_card_with_otp(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "settings.json"
    config_payload = build_private_runtime_config_payload(card_count=10)
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")
    monkeypatch.setenv("PAYNKOLAY_CONFIG_FILE", str(config_path))

    response = await client.post(
        "/api/cards",
        json={
            "alias": "manual_3ds_card",
            "brand": "mastercard",
            "card_number": "5555555555554444",
            "expiry_month": 11,
            "expiry_year": 2031,
            "cvv": "999",
            "flow_type": "secure",
            "expected_otp": "123456",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["alias"] == "manual_3ds_card"
    assert payload["flow_type"] == "secure"
    assert payload["requires_3ds"] is True
    updated = json.loads(config_path.read_text(encoding="utf-8"))
    cards = updated["environments"]["dev"]["cards"]
    assert cards[-1]["expected_otp"] == "123456"


@pytest.mark.api
@pytest.mark.asyncio
async def test_cards_route_rejects_duplicate_alias(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "settings.json"
    config_payload = build_private_runtime_config_payload(card_count=10)
    environments = cast(dict[str, Any], config_payload["environments"])
    dev = cast(dict[str, Any], environments["dev"])
    cards = cast(list[dict[str, Any]], dev["cards"])
    duplicate_alias = str(cards[0]["alias"])
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")
    monkeypatch.setenv("PAYNKOLAY_CONFIG_FILE", str(config_path))

    response = await client.post(
        "/api/cards",
        json={
            "alias": duplicate_alias,
            "brand": "visa",
            "card_number": "4111111111111234",
            "expiry_month": 10,
            "expiry_year": 2030,
            "cvv": "321",
            "flow_type": "moto",
        },
    )

    assert response.status_code == 409
    assert "card alias already exists" in response.json()["detail"]


@pytest.mark.api
@pytest.mark.asyncio
async def test_cards_route_requires_otp_for_3ds_card(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/cards",
        json={
            "alias": "manual_3ds_without_otp",
            "brand": "visa",
            "card_number": "4111111111111234",
            "expiry_month": 10,
            "expiry_year": 2030,
            "cvv": "321",
            "flow_type": "secure",
        },
    )

    assert response.status_code == 422
    assert "expected_otp is required" in response.text


@pytest.mark.api
@pytest.mark.asyncio
async def test_parallel_run_manual_mode_repeats_selected_cards(
    client: httpx.AsyncClient,
    fake_initializer: FakePaymentInitializer,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_parallel_runtime_config(
        monkeypatch,
        tmp_path,
        [
            _runtime_card(
                alias="parallel_moto",
                pan="4111111111111111",
                requires_3ds=False,
            ),
        ],
    )
    fake_initializer.provider_result = _payment_result(
        response_code="2",
        response_data="Islem Basarili",
    )

    response = await client.post(
        "/api/parallel-runs",
        json={
            "mode": "manual",
            "amount": "100.00",
            "currency": "TRY",
            "concurrency": 2,
            "manual_cards": [{"alias": "parallel_moto", "repeat_count": 2}],
        },
    )

    assert response.status_code == 202
    payload = await _wait_parallel_run(client, response.json()["run_id"])
    assert payload["status"] == "completed"
    assert payload["total"] == 2
    assert payload["completed"] == 2
    assert payload["failed"] == 0
    assert [item["attempt_index"] for item in payload["items"]] == [1, 2]
    assert {item["classification"] for item in payload["items"]} == {"completed"}
    assert all(item["payment_list_status"] == "captured" for item in payload["items"])
    assert len(fake_initializer.calls) == 2
    assert "4111111111111111" not in response.text


@pytest.mark.api
@pytest.mark.asyncio
async def test_parallel_run_records_3ds_items_as_pending_without_browser_execution(
    client: httpx.AsyncClient,
    fake_initializer: FakePaymentInitializer,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_parallel_runtime_config(
        monkeypatch,
        tmp_path,
        [
            _runtime_card(
                alias="parallel_3ds",
                pan="5555555555554444",
                requires_3ds=True,
                expected_otp="123456",
            ),
        ],
    )

    response = await client.post(
        "/api/parallel-runs",
        json={
            "mode": "manual",
            "amount": "50.00",
            "currency": "TRY",
            "concurrency": 1,
            "manual_cards": [{"alias": "parallel_3ds", "repeat_count": 1}],
        },
    )

    assert response.status_code == 202
    payload = await _wait_parallel_run(client, response.json()["run_id"])
    assert payload["status"] == "completed"
    assert payload["items"][0]["classification"] == "pending_3ds"
    assert payload["items"][0]["requires_3ds"] is True
    assert payload["items"][0]["three_ds_url"].startswith("/payments/batch-")
    assert fake_initializer.status_calls == []


@pytest.mark.api
@pytest.mark.asyncio
async def test_parallel_run_continues_when_one_item_fails(
    client: httpx.AsyncClient,
    fake_initializer: FakePaymentInitializer,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_parallel_runtime_config(
        monkeypatch,
        tmp_path,
        [
            _runtime_card(
                alias="parallel_moto",
                pan="4111111111111111",
                requires_3ds=False,
            ),
        ],
    )
    network_cause = OSError("[Errno 8] nodename nor servname provided")
    fake_initializer.outcomes = [
        PaymentProviderInitializationError("provider payment initialization failed"),
        _payment_result(response_code="2", response_data="Islem Basarili"),
    ]
    fake_initializer.outcomes[0].__cause__ = network_cause

    response = await client.post(
        "/api/parallel-runs",
        json={
            "mode": "manual",
            "amount": "100.00",
            "currency": "TRY",
            "concurrency": 2,
            "manual_cards": [{"alias": "parallel_moto", "repeat_count": 2}],
        },
    )

    assert response.status_code == 202
    payload = await _wait_parallel_run(client, response.json()["run_id"])
    assert payload["status"] == "completed_with_failures"
    assert payload["completed"] == 1
    assert payload["failed"] == 1
    assert [item["classification"] for item in payload["items"]] == [
        "network_error",
        "completed",
    ]
    assert len(fake_initializer.calls) == 2


@pytest.mark.api
@pytest.mark.asyncio
async def test_parallel_run_rejects_unknown_manual_card(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_parallel_runtime_config(
        monkeypatch,
        tmp_path,
        [
            _runtime_card(
                alias="parallel_moto",
                pan="4111111111111111",
                requires_3ds=False,
            ),
        ],
    )

    response = await client.post(
        "/api/parallel-runs",
        json={
            "mode": "manual",
            "amount": "100.00",
            "currency": "TRY",
            "manual_cards": [{"alias": "missing_card", "repeat_count": 1}],
        },
    )

    assert response.status_code == 422
    assert "unknown card alias" in response.json()["detail"]


@pytest.mark.api
@pytest.mark.asyncio
async def test_parallel_run_random_mode_excludes_synthetic_cards(
    client: httpx.AsyncClient,
    fake_initializer: FakePaymentInitializer,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_parallel_runtime_config(
        monkeypatch,
        tmp_path,
        [
            _runtime_card(
                alias="real_moto",
                pan="4111111111111111",
                requires_3ds=False,
            ),
            _runtime_card(
                alias="synthetic_env1_card_0001",
                pan="5555555555554444",
                requires_3ds=False,
            ),
        ],
    )
    fake_initializer.provider_result = _payment_result(
        response_code="2",
        response_data="Islem Basarili",
    )

    response = await client.post(
        "/api/parallel-runs",
        json={
            "mode": "random",
            "amount": "100.00",
            "currency": "TRY",
            "concurrency": 2,
            "random_count": 3,
        },
    )

    assert response.status_code == 202
    payload = await _wait_parallel_run(client, response.json()["run_id"])
    assert {item["card_alias"] for item in payload["items"]} == {"real_moto"}
    assert len(fake_initializer.calls) == 3


@pytest.mark.api
@pytest.mark.asyncio
async def test_parallel_run_validation_limits_manual_items(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/parallel-runs",
        json={
            "mode": "manual",
            "amount": "100.00",
            "currency": "TRY",
            "manual_cards": [
                {"alias": "a", "repeat_count": 6},
                {"alias": "b", "repeat_count": 5},
            ],
        },
    )

    assert response.status_code == 422
    assert "manual mode can create at most 10 test items" in response.text


@pytest.mark.api
@pytest.mark.asyncio
async def test_installment_options_returns_local_stub_options_for_try(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/installments/options",
        json={
            "amount": "500.00",
            "currency": "TRY",
            "card_brand": "visa",
            "card_number": "4111111111111111",
            "requires_3ds": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "local_stub"
    assert payload["default_installment"] == 1
    assert [option["installment_count"] for option in payload["options"]] == [
        1,
        2,
        3,
        6,
        9,
        12,
    ]
    assert payload["options"][0]["label"] == "Tek cekim"
    assert payload["options"][1]["monthly_amount"] == "250.00"


@pytest.mark.api
@pytest.mark.asyncio
async def test_installment_options_returns_single_payment_for_small_or_foreign_amount(
    client: httpx.AsyncClient,
) -> None:
    small_response = await client.post(
        "/api/installments/options",
        json={
            "amount": "20.00",
            "currency": "TRY",
            "card_brand": "visa",
            "card_number": "4111111111111111",
            "requires_3ds": False,
        },
    )
    foreign_response = await client.post(
        "/api/installments/options",
        json={
            "amount": "500.00",
            "currency": "USD",
            "card_brand": "visa",
            "card_number": "4111111111111111",
            "requires_3ds": False,
        },
    )

    assert small_response.status_code == 200
    assert foreign_response.status_code == 200
    assert [option["installment_count"] for option in small_response.json()["options"]] == [1]
    assert [option["installment_count"] for option in foreign_response.json()["options"]] == [1]


@pytest.mark.api
@pytest.mark.asyncio
async def test_config_overview_reports_missing_runtime_without_secrets(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PAYNKOLAY_CONFIG_FILE", raising=False)

    response = await client.get("/api/config/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime_configured"] is False
    assert payload["readiness"]["checked"] is False
    assert payload["card_count"] == 0
    assert payload["cards"] == []
    assert "PAYNKOLAY_CONFIG_FILE" in payload["message"]


@pytest.mark.api
@pytest.mark.asyncio
async def test_config_overview_exposes_safe_runtime_metadata(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "settings.json"
    scenario_path = tmp_path / "scenarios.json"
    config_payload = build_private_runtime_config_payload(card_count=100)
    environments = cast(dict[str, Any], config_payload["environments"])
    dev = cast(dict[str, Any], environments["dev"])
    dev["callback_base_url"] = "https://merchant-callback.test"
    merchant = cast(dict[str, Any], dev["merchant"])
    merchant.update(
        {
            "merchant_id": "merchant-1001",
            "terminal_id": "terminal-1001",
            "api_key": "payment-api-key-1001",
            "list_api_key": "list-api-key-1001",
            "cancel_refund_api_key": "refund-api-key-1001",
            "secret_key": "merchant-secret-1001",
        }
    )
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")
    scenario_path.write_text(
        json.dumps(build_private_scenario_catalog_payload(card_count=100)),
        encoding="utf-8",
    )
    monkeypatch.setenv("PAYNKOLAY_CONFIG_FILE", str(config_path))
    monkeypatch.setenv("PAYNKOLAY_SCENARIO_CATALOG", str(scenario_path))

    response = await client.get("/api/config/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime_configured"] is True
    assert payload["active_environment"] == "dev"
    assert payload["merchant"]["merchant_id"].startswith("me")
    assert payload["merchant"]["has_list_key"] is True
    assert "merchant-1001" not in response.text
    assert "payment-api-key-1001" not in response.text
    assert "list-api-key-1001" not in response.text
    assert "merchant-secret-1001" not in response.text
    assert payload["card_count"] == 100
    assert payload["scenarios"]["scenario_count"] == 109
    assert payload["scenarios"]["coverage"]["three_ds_count"] > 0
    assert payload["scenarios"]["coverage"]["moto_count"] > 0
    assert payload["scenarios"]["coverage"]["single_payment_count"] > 0
    assert payload["scenarios"]["coverage"]["installment_count"] > 0
    assert payload["scenarios"]["coverage"]["negative_count"] > 0
    assert payload["scenarios"]["coverage"]["payment_channel_counts"]["e_commerce"] > 0
    assert payload["scenarios"]["coverage"]["payment_channel_counts"]["moto"] > 0
    assert payload["scenarios"]["coverage"]["final_status_counts"]["failed"] > 0
    assert payload["readiness"]["checked"] is True
    assert payload["readiness"]["ready"] is True
    assert payload["readiness"]["issues"] == []
    assert payload["cards"][0] == {
        "alias": "visa_3ds_success",
        "brand": "visa",
        "requires_3ds": True,
        "has_expected_otp": True,
    }


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
    assert fake_initializer.status_calls == []
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
async def test_payment_lookup_returns_completed_session_for_result_screen() -> None:
    final_result = PaynkolayPaymentResult.model_validate(
        {
            "RESPONSE_CODE": "2",
            "RESPONSE_DATA": "Islem Basarili",
            "USE_3D": "false",
            "RND": "rnd-lookup",
            "MERCHANT_NO": "merchant-web",
            "AUTH_CODE": "AUTHLOOKUP",
            "REFERENCE_CODE": "ref-lookup",
            "CLIENT_REFERENCE_CODE": "order-result-lookup",
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
        create_response = await client.post(
            "/api/payments",
            json={
                "order_id": "order-result-lookup",
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
        lookup_response = await client.get("/api/payments/order-result-lookup")

    assert create_response.status_code == 202
    assert lookup_response.status_code == 200
    payload = lookup_response.json()
    assert payload["status"] == "completed"
    assert payload["provider_transaction_id"] == "ref-lookup"
    assert payload["payment_list"] == {
        "status": "captured",
        "provider_transaction_id": "list-ref-1001",
        "authorization_code": "LISTAUTH",
        "failure_code": None,
        "updated_at": "2026-07-07T12:00:00+00:00",
        "error": None,
    }
    assert payload["failure_reason"] is None
    assert payload["links"] == {"result": "/result?order_id=order-result-lookup"}
    assert "4111111111111111" not in lookup_response.text
    assert "123" not in lookup_response.text


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
    assert payload["payment_list"] == {
        "status": "captured",
        "provider_transaction_id": "list-ref-1001",
        "authorization_code": "LISTAUTH",
        "failure_code": None,
        "updated_at": "2026-07-07T12:00:00+00:00",
        "error": None,
    }
    assert payload["three_ds"] is None


@pytest.mark.api
@pytest.mark.asyncio
async def test_payment_form_records_paynkolay_moto_provider_result_variant() -> None:
    final_result = PaynkolayPaymentResult.model_validate(
        {
            "RESPONSE_CODE": 2,
            "RESPONSE_DATA": "İşlem Başarılı",
            "USE_3D": "false",
            "RND": "1783940656135",
            "MERCHANT_NO": "400000273",
            "AUTH_CODE": "462514",
            "REFERENCE_CODE": "IKSIRPF530362",
            "CLIENT_REFERENCE_CODE": "order-web-moto-variant",
            "TimeStamp": None,
            "TRANSACTION_AMOUNT": "22.00",
            "AUTHORIZATION_AMOUNT": "22.00",
            "INSTALLMENT": "1",
            "CURRENCY_CODE": Currency.TRY,
            "BANK_REQUEST_MESSAGE": None,
            "hashDatav2": "hash",
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
                "order_id": "order-web-moto-variant",
                "amount": "22.00",
                "currency": "TRY",
                "card_number": "4546711234567894",
                "card_holder": "PAYNKOLAY TEST",
                "expiry_month": 12,
                "expiry_year": 2026,
                "cvv": "000",
                "requires_3ds": False,
                "installment_count": 1,
            },
        )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["requires_3ds"] is False
    assert payload["provider_transaction_id"] == "IKSIRPF530362"
    assert payload["three_ds"] is None


@pytest.mark.api
@pytest.mark.asyncio
async def test_payment_form_records_provider_declined_init_result() -> None:
    declined_result = PaynkolayPaymentResult.model_validate(
        {
            "RESPONSE_CODE": 0,
            "RESPONSE_DATA": "İşlem Başarısız.",
            "TRANSACTION_AMOUNT": "22,00",
            "TimeStamp": "7/13/2026 2:05:18 PM",
            "BANK_REQUEST_MESSAGE": None,
            "hashDatav2": "declined-hash",
        }
    )
    app = create_app()
    app.dependency_overrides[get_payment_initializer] = lambda: FakePaymentInitializer(
        provider_result=declined_result,
        status_fails=True,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/payments",
            json={
                "order_id": "order-web-provider-declined",
                "amount": "22.00",
                "currency": "TRY",
                "card_number": "6501738564461396",
                "card_holder": "PAYNKOLAY TEST",
                "expiry_month": 12,
                "expiry_year": 2026,
                "cvv": "000",
                "requires_3ds": True,
                "installment_count": 1,
            },
        )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["provider_request"] == {
        "client_ref_code": "order-web-provider-declined",
        "amount": "22.00",
        "currency": "TRY",
        "use_3d": True,
        "installment_no": 1,
        "card_brand": "visa",
        "masked_pan": "650173******1396",
        "expiry_month": 12,
        "expiry_year": 2026,
        "transaction_type": "SALES",
        "payment_channel": "e_commerce",
        "success_url": "https://merchant.example.test/payments/result/success",
        "fail_url": "https://merchant.example.test/payments/result/fail",
    }
    assert payload["provider_response_code"] == "0"
    assert payload["provider_response_data"] == "İşlem Başarısız."
    assert payload["failure_reason"] == "İşlem Başarısız."
    assert "Provider code=0" in payload["message"]
    assert "provider message=İşlem Başarısız." in payload["message"]
    assert "VISA 650173******1396" in payload["message"]
    assert payload["three_ds"] is None
    assert "6501738564461396" not in response.text
    assert "000" not in response.text


@pytest.mark.api
@pytest.mark.asyncio
async def test_payment_form_keeps_final_result_when_payment_list_verification_fails() -> None:
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
        provider_result=final_result,
        status_fails=True,
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
    assert payload["provider_response_code"] == "2"
    assert payload["provider_response_data"] == "Islem Basarili"
    assert "Provider code=2" in payload["message"]
    assert "provider message=Islem Basarili" in payload["message"]
    assert payload["payment_list"] == {
        "status": None,
        "provider_transaction_id": None,
        "authorization_code": None,
        "failure_code": None,
        "updated_at": None,
        "error": "provider payment status verification failed",
    }


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
