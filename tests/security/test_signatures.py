from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import SecretStr

from paynkolay_pos.models import Currency
from paynkolay_pos.security import (
    SignatureAlgorithm,
    canonicalize_fields,
    generate_hmac_signature,
    verify_hmac_signature,
)

SIGNATURE_FIELDS = (
    "merchant_id",
    "order_id",
    "amount",
    "currency",
    "requires_3ds",
)


@pytest.mark.api
def test_canonicalize_fields_uses_explicit_order_and_normalized_values() -> None:
    canonical_payload = canonicalize_fields(
        {
            "currency": Currency.TRY,
            "merchant_id": " merchant-dev ",
            "requires_3ds": True,
            "order_id": "order-1001",
            "amount": Decimal("100.00"),
        },
        SIGNATURE_FIELDS,
    )

    assert canonical_payload == "merchant-dev|order-1001|100.00|TRY|true"


@pytest.mark.negative
def test_canonicalize_fields_rejects_missing_required_field() -> None:
    with pytest.raises(ValueError, match="missing signature field: amount"):
        canonicalize_fields(
            {"merchant_id": "merchant-dev", "order_id": "order-1001"},
            SIGNATURE_FIELDS,
        )


@pytest.mark.api
def test_generate_and_verify_hmac_sha256_signature() -> None:
    canonical_payload = "merchant-dev|order-1001|100.00|TRY|true"
    signature = generate_hmac_signature(
        secret_key=SecretStr("test-secret"),
        canonical_payload=canonical_payload,
    )

    assert signature == "c8b9ab5563045c238b6cea6b401a560895a9b75c65298997ab1c510b33ac350a"
    assert verify_hmac_signature(
        secret_key=SecretStr("test-secret"),
        canonical_payload=canonical_payload,
        expected_signature=signature,
    )
    assert not verify_hmac_signature(
        secret_key=SecretStr("wrong-secret"),
        canonical_payload=canonical_payload,
        expected_signature=signature,
    )


@pytest.mark.api
def test_generate_hmac_sha512_signature_when_provider_requires_it() -> None:
    signature = generate_hmac_signature(
        secret_key="test-secret",
        canonical_payload="merchant-dev|order-1001|100.00|TRY|true",
        algorithm=SignatureAlgorithm.HMAC_SHA512,
    )

    assert len(signature) == 128
