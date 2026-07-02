"""Signature verification for provider callback payloads."""

from __future__ import annotations

from pydantic import SecretStr

from paynkolay_pos.models import CallbackPayload
from paynkolay_pos.security import (
    SignatureAlgorithm,
    canonicalize_fields,
    verify_hmac_signature,
)

CALLBACK_SIGNATURE_FIELDS = (
    "order_id",
    "provider_transaction_id",
    "status",
    "amount",
    "currency",
    "received_at",
)


class CallbackSignatureVerificationError(ValueError):
    """Raised when a callback signature does not match its payload."""


def canonicalize_callback_signature_payload(callback: CallbackPayload) -> str:
    """Build the provider-ordered callback payload used for HMAC verification."""

    return canonicalize_fields(callback.signature_payload(), CALLBACK_SIGNATURE_FIELDS)


def verify_callback_signature(
    callback: CallbackPayload,
    *,
    secret_key: SecretStr | str,
    algorithm: SignatureAlgorithm = SignatureAlgorithm.HMAC_SHA256,
) -> bool:
    """Return whether the callback signature matches its canonical payload."""

    canonical_payload = canonicalize_callback_signature_payload(callback)
    return verify_hmac_signature(
        secret_key=secret_key,
        canonical_payload=canonical_payload,
        expected_signature=callback.signature,
        algorithm=algorithm,
    )


def require_valid_callback_signature(
    callback: CallbackPayload,
    *,
    secret_key: SecretStr | str,
    algorithm: SignatureAlgorithm = SignatureAlgorithm.HMAC_SHA256,
) -> CallbackPayload:
    """Return the callback when valid, otherwise raise a domain-specific error."""

    if verify_callback_signature(callback, secret_key=secret_key, algorithm=algorithm):
        return callback
    raise CallbackSignatureVerificationError(
        f"callback signature verification failed for order_id={callback.order_id}"
    )
