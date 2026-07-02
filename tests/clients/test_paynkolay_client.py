from __future__ import annotations

import httpx
import pytest

from paynkolay_pos.clients import PaynkolayClient
from paynkolay_pos.config import RuntimeSettings


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
