from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import SecretStr, ValidationError

from paynkolay_pos.models import (
    Currency,
    PaymentStatus,
    PaynkolayPaymentResult,
    PaynkolayThreeDSInitializeResult,
    parse_paynkolay_payment_result,
)

PAYMENT_RESULT_HASH = (
    "38SwgQiVN8mLKWAp8FBikefhiWPm+8qu+w83hxgqrGEVS+7I+V6T2KoWoaUtVCES8knU5Uu/GatucjiZe/zqLA=="
)


def successful_result_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "RESPONSE_CODE": "2",
        "RESPONSE_DATA": "Islem Basarili",
        "USE_3D": "true",
        "RND": "1630051651137",
        "MERCHANT_NO": "400000001",
        "AUTH_CODE": "S00586",
        "REFERENCE_CODE": "IKSIRPF102168",
        "CLIENT_REFERENCE_CODE": "order-1001",
        "TIMESTAMP": "2026-07-03 09:45:00.000",
        "TRANSACTION_AMOUNT": "1.00",
        "AUTHORIZATION_AMOUNT": "1.00",
        "COMMISION": "0.00",
        "COMMISION_RATE": "0.0000",
        "INSTALLMENT": "1",
        "CURRENCY_CODE": "TRY",
        "hashData": "legacy-hash",
        "hashDataV2": PAYMENT_RESULT_HASH,
    }
    payload.update(overrides)
    return payload


@pytest.mark.api
def test_parse_paynkolay_3ds_initialize_result() -> None:
    result = parse_paynkolay_payment_result(
        {"BANK_REQUEST_MESSAGE": "<form>3DS challenge</form>"}
    )

    assert isinstance(result, PaynkolayThreeDSInitializeResult)
    assert result.status is PaymentStatus.PENDING_3DS
    assert result.bank_request_message == "<form>3DS challenge</form>"


@pytest.mark.api
def test_payment_result_verifies_hash_and_maps_success_status() -> None:
    result = PaynkolayPaymentResult.model_validate(successful_result_payload())

    assert result.response_code == "2"
    assert result.auth_code == "S00586"
    assert result.authorization_amount == Decimal("1.00")
    assert result.currency_code is Currency.TRY
    assert result.successful is True
    assert result.status is PaymentStatus.CAPTURED
    assert result.expected_hash(SecretStr("merchant-secret")) == PAYMENT_RESULT_HASH
    assert result.verify_hash(SecretStr("merchant-secret"))
    assert not result.verify_hash(SecretStr("wrong-secret"))


@pytest.mark.api
@pytest.mark.parametrize("auth_code", ["", "0", "00"])
def test_payment_result_requires_real_auth_code_for_success(auth_code: str) -> None:
    result = PaynkolayPaymentResult.model_validate(
        successful_result_payload(AUTH_CODE=auth_code)
    )

    assert result.successful is False
    assert result.status is PaymentStatus.FAILED


@pytest.mark.api
def test_payment_result_treats_non_success_response_code_as_failed() -> None:
    result = PaynkolayPaymentResult.model_validate(
        successful_result_payload(RESPONSE_CODE="99")
    )

    assert result.successful is False
    assert result.status is PaymentStatus.FAILED


@pytest.mark.negative
def test_payment_result_requires_hash_data_v2() -> None:
    payload = successful_result_payload()
    del payload["hashDataV2"]

    with pytest.raises(ValidationError, match="hashDataV2"):
        PaynkolayPaymentResult.model_validate(payload)


@pytest.mark.api
def test_parse_paynkolay_payment_result_uses_result_payload_when_no_3ds_html() -> None:
    result = parse_paynkolay_payment_result(successful_result_payload())

    assert isinstance(result, PaynkolayPaymentResult)
    assert result.reference_code == "IKSIRPF102168"
