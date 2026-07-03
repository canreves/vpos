from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import SecretStr

from paynkolay_pos.security import (
    PAYMENT_REQUEST_HASH_FIELDS,
    canonicalize_paynkolay_hash_fields,
    generate_cancel_refund_hash,
    generate_payment_list_hash,
    generate_payment_request_hash,
    generate_payment_response_hash,
    generate_sha512_base64_hash,
    verify_sha512_base64_hash,
)

PAYMENT_REQUEST_HASH = (
    "SrKuemmhr7qEX3c/QyU9QzjjbR69A3Go1y0TCRozkGlIER/4kJxf+gAHvjKNEgCEgCCkgCJSaAU4v7CoatJP9A=="
)
PAYMENT_RESPONSE_HASH = (
    "38SwgQiVN8mLKWAp8FBikefhiWPm+8qu+w83hxgqrGEVS+7I+V6T2KoWoaUtVCES8knU5Uu/GatucjiZe/zqLA=="
)
PAYMENT_LIST_HASH = (
    "/ffJQVrOejZblnpU2wgKwhga8UI1ilv7wQzJaUDneJRjZHdKm/p2jxRJKha+d14qJcMsfj4TCrYzfR8dCc5/lg=="
)
CANCEL_REFUND_HASH = (
    "pSC7k/bnXszZonnIkRnLfw5vpSJa3emSHoBGPXOeOjF18//Uh4ioNuLVm5qnT62+G8zxfH86O5xDKxmYQ0O/tg=="
)


@pytest.mark.api
def test_canonicalize_paynkolay_hash_fields_preserves_order_and_empty_values() -> None:
    canonical_payload = canonicalize_paynkolay_hash_fields(
        {
            "sx": SecretStr("sx-token"),
            "clientRefCode": "order-1001",
            "amount": Decimal("100"),
            "successUrl": "https://merchant.test/success",
            "failUrl": "https://merchant.test/fail",
            "rnd": "03-07-2026 09:45:00",
            "customerKey": "",
            "merchantSecretKey": SecretStr("merchant-secret"),
        },
        PAYMENT_REQUEST_HASH_FIELDS,
    )

    assert (
        canonical_payload
        == "sx-token|order-1001|100.00|https://merchant.test/success|"
        "https://merchant.test/fail|03-07-2026 09:45:00||merchant-secret"
    )


@pytest.mark.negative
def test_canonicalize_paynkolay_hash_fields_rejects_missing_fields() -> None:
    with pytest.raises(ValueError, match="missing Paynkolay hash field: amount"):
        canonicalize_paynkolay_hash_fields(
            {
                "sx": "sx-token",
                "clientRefCode": "order-1001",
            },
            PAYMENT_REQUEST_HASH_FIELDS,
        )


@pytest.mark.api
def test_generate_and_verify_sha512_base64_hash() -> None:
    canonical_payload = (
        "sx-token|order-1001|100.00|https://merchant.test/success|"
        "https://merchant.test/fail|03-07-2026 09:45:00||merchant-secret"
    )
    generated_hash = generate_sha512_base64_hash(canonical_payload)

    assert generated_hash == PAYMENT_REQUEST_HASH
    assert verify_sha512_base64_hash(
        canonical_payload=canonical_payload,
        expected_hash=generated_hash,
    )
    assert not verify_sha512_base64_hash(
        canonical_payload=canonical_payload,
        expected_hash="wrong-hash",
    )


@pytest.mark.api
def test_generate_payment_request_hash_matches_paynkolay_field_order() -> None:
    generated_hash = generate_payment_request_hash(
        sx=SecretStr("sx-token"),
        client_ref_code="order-1001",
        amount=Decimal("100"),
        success_url="https://merchant.test/success",
        fail_url="https://merchant.test/fail",
        rnd="03-07-2026 09:45:00",
        customer_key="",
        merchant_secret_key=SecretStr("merchant-secret"),
    )

    assert generated_hash == PAYMENT_REQUEST_HASH


@pytest.mark.api
def test_generate_payment_response_hash_matches_paynkolay_field_order() -> None:
    generated_hash = generate_payment_response_hash(
        merchant_no="400000001",
        reference_code="IKSIRPF102168",
        auth_code="S00586",
        response_code="2",
        use_3d=True,
        rnd="1630051651137",
        installment=1,
        authorization_amount=Decimal("1"),
        currency_code="TRY",
        merchant_secret_key=SecretStr("merchant-secret"),
    )

    assert generated_hash == PAYMENT_RESPONSE_HASH


@pytest.mark.api
def test_generate_payment_list_hash_matches_paynkolay_field_order() -> None:
    generated_hash = generate_payment_list_hash(
        sx=SecretStr("sx-list"),
        start_date="01.07.2026",
        end_date="31.07.2026",
        client_ref_code="order-1001",
        merchant_secret_key=SecretStr("merchant-secret"),
    )

    assert generated_hash == PAYMENT_LIST_HASH


@pytest.mark.api
def test_generate_cancel_refund_hash_matches_paynkolay_field_order() -> None:
    generated_hash = generate_cancel_refund_hash(
        sx=SecretStr("sx-cancel"),
        reference_code="IKSIRPF102168",
        transaction_type="cancel",
        amount=Decimal("100"),
        trx_date="2026.07.03",
        merchant_secret_key=SecretStr("merchant-secret"),
    )

    assert generated_hash == CANCEL_REFUND_HASH
