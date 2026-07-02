"""Deterministic canonicalization and HMAC helpers for payment payloads."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping, Sequence
from decimal import Decimal
from enum import StrEnum

from pydantic import SecretStr


class SignatureAlgorithm(StrEnum):
    """Supported request and callback signature algorithms."""

    HMAC_SHA256 = "hmac-sha256"
    HMAC_SHA512 = "hmac-sha512"


_DIGESTS = {
    SignatureAlgorithm.HMAC_SHA256: hashlib.sha256,
    SignatureAlgorithm.HMAC_SHA512: hashlib.sha512,
}


def _canonical_value(value: object) -> str:
    """Convert supported primitive values into deterministic signature text."""

    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    raise TypeError(f"unsupported signature field type: {type(value).__name__}")


def canonicalize_fields(
    payload: Mapping[str, object],
    field_order: Sequence[str],
    *,
    separator: str = "|",
) -> str:
    """Join payload fields in provider-defined order for signing.

    Missing fields are rejected because silently signing an empty value can hide payment
    integration bugs. Optional provider fields should be omitted from ``field_order``.
    """

    canonical_parts: list[str] = []
    for field_name in field_order:
        if field_name not in payload:
            raise ValueError(f"missing signature field: {field_name}")
        canonical_parts.append(_canonical_value(payload[field_name]))
    return separator.join(canonical_parts)


def generate_hmac_signature(
    *,
    secret_key: SecretStr | str,
    canonical_payload: str,
    algorithm: SignatureAlgorithm = SignatureAlgorithm.HMAC_SHA256,
) -> str:
    """Generate a hexadecimal HMAC signature for a canonical payload."""

    key = secret_key.get_secret_value() if isinstance(secret_key, SecretStr) else secret_key
    digest = _DIGESTS[algorithm]
    return hmac.new(
        key=key.encode("utf-8"),
        msg=canonical_payload.encode("utf-8"),
        digestmod=digest,
    ).hexdigest()


def verify_hmac_signature(
    *,
    secret_key: SecretStr | str,
    canonical_payload: str,
    expected_signature: str,
    algorithm: SignatureAlgorithm = SignatureAlgorithm.HMAC_SHA256,
) -> bool:
    """Verify a hexadecimal HMAC signature using constant-time comparison."""

    actual_signature = generate_hmac_signature(
        secret_key=secret_key,
        canonical_payload=canonical_payload,
        algorithm=algorithm,
    )
    return hmac.compare_digest(actual_signature, expected_signature)
