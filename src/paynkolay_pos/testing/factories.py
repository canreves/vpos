"""Factory helpers for deterministic payment and callback test data."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import SecretStr

from paynkolay_pos.callbacks import canonicalize_callback_signature_payload
from paynkolay_pos.models import (
    CallbackPayload,
    PaymentInitializeRequest,
    PaymentStatus,
    TransactionStatusResponse,
)
from paynkolay_pos.security import SignatureAlgorithm, generate_hmac_signature


def _status_value(status: PaymentStatus | str) -> str:
    return status.value if isinstance(status, PaymentStatus) else status


def payment_card_payload(**overrides: object) -> dict[str, object]:
    """Build a valid card payload for payment initialization tests."""

    payload: dict[str, object] = {
        "brand": "visa",
        "pan": "4111111111111111",
        "expiry_month": 12,
        "expiry_year": 2030,
        "cvv": "123",
    }
    payload.update(overrides)
    return payload


def payment_initialize_request_payload(
    *,
    card: Mapping[str, object] | None = None,
    **overrides: object,
) -> dict[str, object]:
    """Build a valid payment initialization request payload."""

    payload: dict[str, object] = {
        "merchant_id": "merchant-dev",
        "terminal_id": "terminal-dev",
        "order_id": "order-1001",
        "amount": "100.00",
        "currency": "TRY",
        "callback_url": "https://merchant-dev.example.test/callback",
        "card": dict(card) if card is not None else payment_card_payload(),
        "requires_3ds": True,
        "correlation_id": "corr-1001",
    }
    payload.update(overrides)
    return payload


def payment_initialize_request(
    *,
    card: Mapping[str, object] | None = None,
    **overrides: object,
) -> PaymentInitializeRequest:
    """Build a validated payment initialization request model."""

    return PaymentInitializeRequest.model_validate(
        payment_initialize_request_payload(card=card, **overrides)
    )


def transaction_status_response_payload(
    status: PaymentStatus | str = PaymentStatus.CAPTURED,
    **overrides: object,
) -> dict[str, object]:
    """Build a valid transaction status response payload."""

    status_value = _status_value(status)
    payload: dict[str, object] = {
        "order_id": "order-1001",
        "provider_transaction_id": "txn-1001",
        "status": status_value,
        "amount": "100.00",
        "currency": "TRY",
        "updated_at": "2026-07-02T12:00:00+03:00",
    }
    if status_value in {"authorized", "captured"}:
        payload["authorization_code"] = "auth-1001"
    if status_value == "failed":
        payload["failure_code"] = "issuer_declined"
    payload.update(overrides)
    return payload


def transaction_status_response(
    status: PaymentStatus | str = PaymentStatus.CAPTURED,
    **overrides: object,
) -> TransactionStatusResponse:
    """Build a validated transaction status response model."""

    return TransactionStatusResponse.model_validate(
        transaction_status_response_payload(status, **overrides)
    )


def callback_payload(
    status: PaymentStatus | str = PaymentStatus.CAPTURED,
    **overrides: object,
) -> dict[str, object]:
    """Build a valid provider callback payload with a placeholder signature."""

    status_value = _status_value(status)
    payload: dict[str, object] = {
        "order_id": "order-1001",
        "provider_transaction_id": "txn-1001",
        "status": status_value,
        "amount": "100.00",
        "currency": "TRY",
        "received_at": "2026-07-02T12:00:00+03:00",
        "signature": "a" * 64,
    }
    if status_value in {"authorized", "captured"}:
        payload["authorization_code"] = "auth-1001"
    if status_value == "failed":
        payload["failure_code"] = "issuer_declined"
    payload.update(overrides)
    return payload


def callback_payload_model(
    status: PaymentStatus | str = PaymentStatus.CAPTURED,
    **overrides: object,
) -> CallbackPayload:
    """Build a validated provider callback model with a placeholder signature."""

    return CallbackPayload.model_validate(callback_payload(status, **overrides))


def signed_callback_payload(
    *,
    secret_key: SecretStr | str = "callback-secret",
    algorithm: SignatureAlgorithm = SignatureAlgorithm.HMAC_SHA256,
    status: PaymentStatus | str = PaymentStatus.CAPTURED,
    **overrides: object,
) -> dict[str, object]:
    """Build a provider callback payload signed with the supplied merchant secret."""

    payload = callback_payload(status, **overrides)
    payload["signature"] = "0" * 64
    callback = CallbackPayload.model_validate(payload)
    payload["signature"] = generate_hmac_signature(
        secret_key=secret_key,
        canonical_payload=canonicalize_callback_signature_payload(callback),
        algorithm=algorithm,
    )
    return payload


def signed_callback_payload_model(
    *,
    secret_key: SecretStr | str = "callback-secret",
    algorithm: SignatureAlgorithm = SignatureAlgorithm.HMAC_SHA256,
    status: PaymentStatus | str = PaymentStatus.CAPTURED,
    **overrides: object,
) -> CallbackPayload:
    """Build a validated provider callback model with a matching HMAC signature."""

    return CallbackPayload.model_validate(
        signed_callback_payload(
            secret_key=secret_key,
            algorithm=algorithm,
            status=status,
            **overrides,
        )
    )
