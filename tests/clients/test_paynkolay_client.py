from __future__ import annotations

import json

import httpx
import pytest

from paynkolay_pos.clients import PaynkolayClient
from paynkolay_pos.config import RuntimeSettings
from paynkolay_pos.models import PaymentStatus
from paynkolay_pos.security import generate_payment_list_hash, generate_payment_request_hash
from paynkolay_pos.testing import payment_initialize_request


def valid_settings_payload() -> dict[str, object]:
    return {
        "active_environment": "dev",
        "environments": {
            "dev": {
                "name": "dev",
                "base_url": "https://dev-pos.example.test",
                "callback_base_url": "https://merchant-dev.example.test",
                "merchant": {
                    "merchant_id": "merchant-dev",
                    "terminal_id": "terminal-dev",
                    "api_key": "api-key-dev",
                    "secret_key": "secret-dev",
                },
                "cards": [
                    {
                        "alias": "visa_3ds_success",
                        "brand": "visa",
                        "pan": "4111111111111111",
                        "expiry_month": 12,
                        "expiry_year": 2030,
                        "cvv": "123",
                        "requires_3ds": True,
                        "expected_otp": "123456",
                    }
                ],
            }
        },
    }


@pytest.mark.api
@pytest.mark.asyncio
async def test_client_posts_json_with_environment_headers() -> None:
    settings = RuntimeSettings.model_validate(valid_settings_payload())
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            status_code=200,
            json={"status": "ok", "echo": request.url.path},
        )

    async with PaynkolayClient(
        settings.current,
        transport=httpx.MockTransport(handler),
    ) as client:
        response = await client.post_json("/payments/initialize", {"order_id": "order-1001"})

    assert response == {"status": "ok", "echo": "/payments/initialize"}
    assert captured_request is not None
    assert str(captured_request.url) == "https://dev-pos.example.test/payments/initialize"
    assert captured_request.headers["X-Merchant-Id"] == "merchant-dev"
    assert captured_request.headers["X-Terminal-Id"] == "terminal-dev"


@pytest.mark.api
@pytest.mark.asyncio
async def test_client_rejects_non_object_json_response() -> None:
    settings = RuntimeSettings.model_validate(valid_settings_payload())

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json=["not", "an", "object"])

    async with PaynkolayClient(
        settings.current,
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(TypeError, match="provider response must be a JSON object"):
            await client.post_json("/payments/initialize", {"order_id": "order-1001"})


@pytest.mark.api
@pytest.mark.asyncio
async def test_client_raises_for_provider_http_errors() -> None:
    settings = RuntimeSettings.model_validate(valid_settings_payload())

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=401, json={"error": "unauthorized"})

    async with PaynkolayClient(
        settings.current,
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await client.post_json("/payments/initialize", {"order_id": "order-1001"})


@pytest.mark.api
@pytest.mark.asyncio
async def test_client_posts_multipart_form_data() -> None:
    settings = RuntimeSettings.model_validate(valid_settings_payload())
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(status_code=200, json={"status": "ok"})

    async with PaynkolayClient(
        settings.current,
        transport=httpx.MockTransport(handler),
    ) as client:
        response = await client.post_form("/v1/Payment", {"clientRefCode": "order-1001"})

    assert response == {"status": "ok"}
    assert captured_request is not None
    assert str(captured_request.url) == "https://dev-pos.example.test/v1/Payment"
    assert captured_request.headers["content-type"].startswith("multipart/form-data")
    assert b'name="clientRefCode"' in captured_request.content
    assert b"order-1001" in captured_request.content


@pytest.mark.api
@pytest.mark.asyncio
async def test_initialize_payment_signs_request_and_parses_response() -> None:
    settings = RuntimeSettings.model_validate(valid_settings_payload())
    captured_payload: dict[str, object] | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content)
        return httpx.Response(
            status_code=200,
            json={
                "order_id": "order-1001",
                "provider_transaction_id": "txn-1001",
                "status": "pending_3ds",
                "amount": "100.00",
                "currency": "TRY",
                "redirect_url": "https://acs.example.test/challenge/order-1001",
            },
        )

    payment_request = payment_initialize_request()

    async with PaynkolayClient(
        settings.current,
        transport=httpx.MockTransport(handler),
    ) as client:
        response = await client.initialize_payment(payment_request)

    assert response.status is PaymentStatus.PENDING_3DS
    assert response.provider_transaction_id == "txn-1001"
    assert captured_payload is not None
    assert captured_payload["signature"] == (
        "e97f9342129169b35e8e760e243dcfc8"
        "33d390f0cbb991c9d8c6d99ac7b88d3f"
    )
    assert captured_payload["card"] == {
        "brand": "visa",
        "pan": "4111111111111111",
        "expiry_month": 12,
        "expiry_year": 2030,
        "cvv": "123",
        "card_holder": "PAYNKOLAY TEST",
    }
    assert captured_payload["installment_count"] == 1
    assert captured_payload["payment_channel"] == "e_commerce"
    assert captured_payload["moto"] is False


@pytest.mark.api
@pytest.mark.asyncio
async def test_payment_form_payload_maps_internal_request_to_paynkolay_fields() -> None:
    settings = RuntimeSettings.model_validate(valid_settings_payload())
    payment_request = payment_initialize_request()

    async with PaynkolayClient(settings.current) as client:
        payload = client.payment_form_payload(
            payment_request,
            success_url="https://merchant.example.test/success",
            fail_url="https://merchant.example.test/fail",
            card_holder_ip=" 185.125.190.58 ",
            rnd="03-07-2026 09:45:00",
        )

    expected_hash = generate_payment_request_hash(
        sx=settings.current.merchant.api_key,
        client_ref_code="order-1001",
        amount="100.00",
        success_url="https://merchant.example.test/success",
        fail_url="https://merchant.example.test/fail",
        rnd="03-07-2026 09:45:00",
        merchant_secret_key=settings.current.merchant.secret_key,
    )
    assert payload == {
        "sx": "api-key-dev",
        "clientRefCode": "order-1001",
        "successUrl": "https://merchant.example.test/success",
        "failUrl": "https://merchant.example.test/fail",
        "amount": "100.00",
        "installmentNo": "1",
        "cardHolderName": "PAYNKOLAY TEST",
        "month": "12",
        "year": "2030",
        "cvv": "123",
        "cardNumber": "4111111111111111",
        "use3D": "true",
        "transactionType": "SALES",
        "cardHolderIP": "185.125.190.58",
        "rnd": "03-07-2026 09:45:00",
        "hashDatav2": expected_hash,
        "environment": "API",
        "currencyNumber": "949",
        "MerchantCustomerNo": "",
    }


@pytest.mark.negative
@pytest.mark.asyncio
async def test_payment_form_payload_rejects_invalid_provider_required_fields() -> None:
    settings = RuntimeSettings.model_validate(valid_settings_payload())
    payment_request = payment_initialize_request()

    async with PaynkolayClient(settings.current) as client:
        with pytest.raises(ValueError, match="success_url must use https"):
            client.payment_form_payload(
                payment_request,
                success_url="http://merchant.example.test/success",
                fail_url="https://merchant.example.test/fail",
                card_holder_ip="185.125.190.58",
                rnd="03-07-2026 09:45:00",
            )

        with pytest.raises(ValueError, match="card_holder_ip must not be empty"):
            client.payment_form_payload(
                payment_request,
                success_url="https://merchant.example.test/success",
                fail_url="https://merchant.example.test/fail",
                card_holder_ip=" ",
                rnd="03-07-2026 09:45:00",
            )


@pytest.mark.api
@pytest.mark.asyncio
async def test_initialize_payment_form_posts_paynkolay_payment_request() -> None:
    settings = RuntimeSettings.model_validate(valid_settings_payload())
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            status_code=200,
            json={"BANK_REQUEST_MESSAGE": "<form>3DS challenge</form>"},
        )

    payment_request = payment_initialize_request()
    async with PaynkolayClient(
        settings.current,
        transport=httpx.MockTransport(handler),
    ) as client:
        response = await client.initialize_payment_form(
            payment_request,
            success_url="https://merchant.example.test/success",
            fail_url="https://merchant.example.test/fail",
            card_holder_ip="185.125.190.58",
            rnd="03-07-2026 09:45:00",
        )

    assert response == {"BANK_REQUEST_MESSAGE": "<form>3DS challenge</form>"}
    assert captured_request is not None
    assert captured_request.method == "POST"
    assert captured_request.url.path == "/v1/Payment"
    assert captured_request.headers["content-type"].startswith("multipart/form-data")
    assert b'name="hashDatav2"' in captured_request.content
    assert b'name="cardNumber"' in captured_request.content


@pytest.mark.api
@pytest.mark.asyncio
async def test_payment_list_form_payload_builds_paynkolay_status_query_fields() -> None:
    settings = RuntimeSettings.model_validate(valid_settings_payload())

    async with PaynkolayClient(settings.current) as client:
        payload = client.payment_list_form_payload(
            start_date="01.07.2026",
            end_date="31.07.2026",
            client_ref_code="order-1001",
        )

    expected_hash = generate_payment_list_hash(
        sx=settings.current.merchant.api_key,
        start_date="01.07.2026",
        end_date="31.07.2026",
        client_ref_code="order-1001",
        merchant_secret_key=settings.current.merchant.secret_key,
    )
    assert payload == {
        "sx": "api-key-dev",
        "startDate": "01.07.2026",
        "endDate": "31.07.2026",
        "clientRefCode": "order-1001",
        "hashDatav2": expected_hash,
    }


@pytest.mark.api
@pytest.mark.asyncio
async def test_get_transaction_status_from_payment_list_posts_query_and_maps_row() -> None:
    settings = RuntimeSettings.model_validate(valid_settings_payload())
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            status_code=200,
            json={
                "id": "",
                "result": {
                    "RESPONSE_CODE": "2",
                    "RESPONSE_DATA": "Islem basarili",
                    "LIST": [
                        {
                            "REFERENCE_CODE": "IKSIRPF102168",
                            "AUTH_CODE": "S00586",
                            "AUTHORIZATION_AMOUNT": "1.00",
                            "TRANSACTION_AMOUNT": "1.00",
                            "CLIENT_REFERENCE_CODE": "order-1001",
                            "STATUS": "SUCCESS",
                            "TRANSACTION_TYPE": "SALES",
                            "TRX_DATE": "03.07.2026 09:45:00",
                            "CARD_HOLDER_NAME": "PAYNKOLAY TEST",
                            "IS_3D": True,
                            "INSTALLMENT_COUNT": "1",
                            "DESCRIPTION": "",
                        }
                    ],
                },
            },
        )

    async with PaynkolayClient(
        settings.current,
        transport=httpx.MockTransport(handler),
    ) as client:
        response = await client.get_transaction_status_from_payment_list(
            " order-1001 ",
            start_date="01.07.2026",
            end_date="31.07.2026",
        )

    assert response.status is PaymentStatus.CAPTURED
    assert response.order_id == "order-1001"
    assert response.provider_transaction_id == "IKSIRPF102168"
    assert response.authorization_code == "S00586"
    assert captured_request is not None
    assert captured_request.url.path == "/Payment/PaymentList"
    assert captured_request.headers["content-type"].startswith("multipart/form-data")
    assert b'name="clientRefCode"' in captured_request.content
    assert b"order-1001" in captured_request.content
    assert b'name="hashDatav2"' in captured_request.content


@pytest.mark.negative
@pytest.mark.asyncio
async def test_get_transaction_status_from_payment_list_rejects_missing_provider_row() -> None:
    settings = RuntimeSettings.model_validate(valid_settings_payload())

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "id": "",
                "result": {
                    "RESPONSE_CODE": "2",
                    "LIST": [],
                },
            },
        )

    async with PaynkolayClient(
        settings.current,
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(
            LookupError,
            match="clientRefCode='order-1001'",
        ):
            await client.get_transaction_status_from_payment_list(
                "order-1001",
                start_date="01.07.2026",
                end_date="31.07.2026",
            )


@pytest.mark.api
@pytest.mark.asyncio
async def test_get_transaction_status_fetches_encoded_order_and_parses_response() -> None:
    settings = RuntimeSettings.model_validate(valid_settings_payload())
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            status_code=200,
            json={
                "order_id": "order 1001",
                "provider_transaction_id": "txn-1001",
                "status": "captured",
                "amount": "100.00",
                "currency": "TRY",
                "updated_at": "2026-07-02T12:00:00+03:00",
                "authorization_code": "auth-1001",
            },
        )

    async with PaynkolayClient(
        settings.current,
        transport=httpx.MockTransport(handler),
    ) as client:
        response = await client.get_transaction_status(" order 1001 ")

    assert response.status is PaymentStatus.CAPTURED
    assert response.authorization_code == "auth-1001"
    assert captured_request is not None
    assert str(captured_request.url) == "https://dev-pos.example.test/payments/order%201001/status"


@pytest.mark.negative
@pytest.mark.asyncio
async def test_get_transaction_status_rejects_blank_order_id() -> None:
    settings = RuntimeSettings.model_validate(valid_settings_payload())

    async with PaynkolayClient(settings.current) as client:
        with pytest.raises(ValueError, match="order_id must not be empty"):
            await client.get_transaction_status("   ")
