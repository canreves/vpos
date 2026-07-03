"""Paynkolay-specific SHA-512/Base64 hash helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
from collections.abc import Mapping, Sequence
from decimal import Decimal
from enum import StrEnum

from pydantic import SecretStr

PAYMENT_REQUEST_HASH_FIELDS = (
    "sx",
    "clientRefCode",
    "amount",
    "successUrl",
    "failUrl",
    "rnd",
    "customerKey",
    "merchantSecretKey",
)

PAYMENT_RESPONSE_HASH_FIELDS = (
    "MERCHANT_NO",
    "REFERENCE_CODE",
    "AUTH_CODE",
    "RESPONSE_CODE",
    "USE_3D",
    "RND",
    "INSTALLMENT",
    "AUTHORIZATION_AMOUNT",
    "CURRENCY_CODE",
    "MERCHANT_SECRET_KEY",
)

PAYMENT_LIST_HASH_FIELDS = (
    "sx",
    "startDate",
    "endDate",
    "clientRefCode",
    "merchantSecretKey",
)

CANCEL_REFUND_HASH_FIELDS = (
    "sx",
    "referenceCode",
    "type",
    "amount",
    "trxDate",
    "merchantSecretKey",
)


def _paynkolay_hash_value(value: object) -> str:
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
        return value
    raise TypeError(f"unsupported Paynkolay hash field type: {type(value).__name__}")


def canonicalize_paynkolay_hash_fields(
    payload: Mapping[str, object],
    field_order: Sequence[str],
    *,
    separator: str = "|",
) -> str:
    """Join Paynkolay hash fields in the exact documented order."""

    canonical_parts: list[str] = []
    for field_name in field_order:
        if field_name not in payload:
            raise ValueError(f"missing Paynkolay hash field: {field_name}")
        canonical_parts.append(_paynkolay_hash_value(payload[field_name]))
    return separator.join(canonical_parts)


def generate_sha512_base64_hash(canonical_payload: str) -> str:
    """Return Paynkolay's SHA-512 digest encoded as Base64 text."""

    digest = hashlib.sha512(canonical_payload.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def verify_sha512_base64_hash(
    *,
    canonical_payload: str,
    expected_hash: str,
) -> bool:
    """Verify a Paynkolay SHA-512/Base64 hash using constant-time comparison."""

    return hmac.compare_digest(
        generate_sha512_base64_hash(canonical_payload),
        expected_hash,
    )


def generate_payment_request_hash(
    *,
    sx: SecretStr | str,
    client_ref_code: str,
    amount: Decimal | str,
    success_url: str,
    fail_url: str,
    rnd: str,
    merchant_secret_key: SecretStr | str,
    customer_key: str = "",
) -> str:
    """Generate the documented payment request ``hashDatav2`` value."""

    canonical_payload = canonicalize_paynkolay_hash_fields(
        {
            "sx": sx,
            "clientRefCode": client_ref_code,
            "amount": amount,
            "successUrl": success_url,
            "failUrl": fail_url,
            "rnd": rnd,
            "customerKey": customer_key,
            "merchantSecretKey": merchant_secret_key,
        },
        PAYMENT_REQUEST_HASH_FIELDS,
    )
    return generate_sha512_base64_hash(canonical_payload)


def generate_payment_response_hash(
    *,
    merchant_no: str,
    reference_code: str,
    auth_code: str,
    response_code: str,
    use_3d: bool | str,
    rnd: str,
    installment: int | str,
    authorization_amount: Decimal | str,
    currency_code: str,
    merchant_secret_key: SecretStr | str,
) -> str:
    """Generate the documented payment result ``hashDataV2`` value."""

    canonical_payload = canonicalize_paynkolay_hash_fields(
        {
            "MERCHANT_NO": merchant_no,
            "REFERENCE_CODE": reference_code,
            "AUTH_CODE": auth_code,
            "RESPONSE_CODE": response_code,
            "USE_3D": use_3d,
            "RND": rnd,
            "INSTALLMENT": installment,
            "AUTHORIZATION_AMOUNT": authorization_amount,
            "CURRENCY_CODE": currency_code,
            "MERCHANT_SECRET_KEY": merchant_secret_key,
        },
        PAYMENT_RESPONSE_HASH_FIELDS,
    )
    return generate_sha512_base64_hash(canonical_payload)


def generate_payment_list_hash(
    *,
    sx: SecretStr | str,
    start_date: str,
    end_date: str,
    client_ref_code: str,
    merchant_secret_key: SecretStr | str,
) -> str:
    """Generate the documented transaction verification/list hash."""

    canonical_payload = canonicalize_paynkolay_hash_fields(
        {
            "sx": sx,
            "startDate": start_date,
            "endDate": end_date,
            "clientRefCode": client_ref_code,
            "merchantSecretKey": merchant_secret_key,
        },
        PAYMENT_LIST_HASH_FIELDS,
    )
    return generate_sha512_base64_hash(canonical_payload)


def generate_cancel_refund_hash(
    *,
    sx: SecretStr | str,
    reference_code: str,
    transaction_type: str,
    amount: Decimal | str,
    trx_date: str,
    merchant_secret_key: SecretStr | str,
) -> str:
    """Generate the documented cancel/refund ``hashDatav2`` value."""

    canonical_payload = canonicalize_paynkolay_hash_fields(
        {
            "sx": sx,
            "referenceCode": reference_code,
            "type": transaction_type,
            "amount": amount,
            "trxDate": trx_date,
            "merchantSecretKey": merchant_secret_key,
        },
        CANCEL_REFUND_HASH_FIELDS,
    )
    return generate_sha512_base64_hash(canonical_payload)
