from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from paynkolay_pos.config import CardBrand
from paynkolay_pos.diagnostics import (
    AcsObservation,
    AcsScreenClassification,
    DiagnosticClassification,
    InitObservation,
    InitOutcome,
    OtpResolutionObservation,
    OtpResolutionStatus,
    OtpSourceType,
    PaymentListObservation,
    PaymentListOutcome,
    ResultMatrixEntry,
    ResultMatrixFlow,
    result_matrix_json,
)
from paynkolay_pos.models import PaymentStatus


def result_entry(**overrides: object) -> ResultMatrixEntry:
    payload: dict[str, object] = {
        "card_alias": "credential_visa_7894_moto_authorized",
        "brand": CardBrand.VISA,
        "flow": ResultMatrixFlow.MOTO,
        "requires_3ds": False,
        "scenario_id": "credential_visa_7894_moto_authorized",
        "order_id": "uat-smoke-1001",
        "init": InitObservation(
            outcome=InitOutcome.FINAL_SUCCESS,
            http_status=200,
            parsed_result_type="PaynkolayPaymentResult",
            provider_response_code="2",
            provider_response_data="Islem Basarili",
        ),
        "acs": AcsObservation(classification=AcsScreenClassification.NOT_APPLICABLE),
        "payment_list": PaymentListObservation(
            outcome=PaymentListOutcome.FOUND,
            status=PaymentStatus.CAPTURED,
            provider_transaction_id_present=True,
            authorization_code_present=True,
        ),
    }
    payload.update(overrides)
    return ResultMatrixEntry.model_validate(payload)


@pytest.mark.api
def test_result_matrix_classifies_completed_moto_payment() -> None:
    entry = result_entry()

    assert entry.classification is DiagnosticClassification.COMPLETED
    assert entry.summary_row() == {
        "card_alias": "credential_visa_7894_moto_authorized",
        "brand": "visa",
        "flow": "moto",
        "requires_3ds": False,
        "scenario_id": "credential_visa_7894_moto_authorized",
        "order_id": "uat-smoke-1001",
        "init_outcome": "final_success",
        "init_http_status": 200,
        "parsed_result_type": "PaynkolayPaymentResult",
        "provider_response_code": "2",
        "provider_response_data": "Islem Basarili",
        "bank_request_message_present": False,
        "acs_classification": "not_applicable",
        "acs_reason": None,
        "callback_returned": False,
        "otp_resolution_status": None,
        "otp_source_type": None,
        "otp_present": None,
        "should_auto_submit": None,
        "payment_list_outcome": "found",
        "payment_list_status": "captured",
        "classification": "completed",
        "notes": [],
    }


@pytest.mark.api
def test_result_matrix_classifies_provider_declined_init() -> None:
    entry = result_entry(
        card_alias="credential_is_bankasi_troy_1396_3ds_success",
        brand=CardBrand.TROY,
        flow=ResultMatrixFlow.THREE_DS,
        requires_3ds=True,
        init=InitObservation(
            outcome=InitOutcome.FINAL_FAILED,
            http_status=200,
            parsed_result_type="PaynkolayPaymentResult",
            provider_response_code="0",
            provider_response_data="Islem Basarisiz.",
        ),
        acs=AcsObservation(classification=AcsScreenClassification.NOT_REACHED),
        payment_list=PaymentListObservation(outcome=PaymentListOutcome.NOT_QUERIED),
    )

    assert entry.classification is DiagnosticClassification.PROVIDER_FAILED


@pytest.mark.api
def test_result_matrix_classifies_acs_manual_dependency() -> None:
    entry = result_entry(
        card_alias="credential_garanti_mastercard_3ds",
        brand=CardBrand.MASTERCARD,
        flow=ResultMatrixFlow.THREE_DS,
        requires_3ds=True,
        init=InitObservation(
            outcome=InitOutcome.THREE_DS_INITIALIZED,
            http_status=200,
            parsed_result_type="PaynkolayThreeDSInitializeResult",
            bank_request_message_present=True,
        ),
        acs=AcsObservation(
            classification=AcsScreenClassification.SMS_MANUAL_REQUIRED,
            otp_input_found=True,
            submit_control_found=True,
            reason="ACS asks for SMS code sent to masked phone",
        ),
        payment_list=PaymentListObservation(outcome=PaymentListOutcome.NOT_QUERIED),
    )

    assert entry.classification is DiagnosticClassification.ACS_MANUAL_REQUIRED


@pytest.mark.api
def test_result_matrix_includes_otp_resolution_columns() -> None:
    entry = result_entry(
        card_alias="credential_visa_3ds",
        flow=ResultMatrixFlow.THREE_DS,
        requires_3ds=True,
        init=InitObservation(
            outcome=InitOutcome.THREE_DS_INITIALIZED,
            parsed_result_type="PaynkolayThreeDSInitializeResult",
            bank_request_message_present=True,
        ),
        acs=AcsObservation(
            classification=AcsScreenClassification.STATIC_CONFIG_OTP,
            otp_input_found=True,
            submit_control_found=True,
        ),
        otp_resolution=OtpResolutionObservation(
            status=OtpResolutionStatus.READY,
            source_type=OtpSourceType.STATIC_CONFIG,
            otp_present=True,
            should_auto_submit=True,
            reason="resolved OTP from configured test card metadata",
        ),
        payment_list=PaymentListObservation(outcome=PaymentListOutcome.NOT_QUERIED),
    )

    row = entry.summary_row()

    assert row["otp_resolution_status"] == "ready"
    assert row["otp_source_type"] == "static_config"
    assert row["otp_present"] is True
    assert row["should_auto_submit"] is True
    assert "654321" not in json.dumps(row)


@pytest.mark.api
def test_result_matrix_classifies_framework_parse_error() -> None:
    entry = result_entry(
        init=InitObservation(
            outcome=InitOutcome.PARSER_ERROR,
            http_status=200,
            error_reason="validation failed",
        ),
        payment_list=PaymentListObservation(outcome=PaymentListOutcome.NOT_QUERIED),
    )

    assert entry.classification is DiagnosticClassification.FRAMEWORK_ERROR


@pytest.mark.api
def test_result_matrix_classifies_network_error_separately() -> None:
    entry = result_entry(
        init=InitObservation(
            outcome=InitOutcome.NETWORK_ERROR,
            error_reason="nodename nor servname provided",
        ),
        payment_list=PaymentListObservation(outcome=PaymentListOutcome.NOT_QUERIED),
    )

    assert entry.classification is DiagnosticClassification.NETWORK_ERROR
    assert entry.summary_row()["classification"] == "network_error"


@pytest.mark.api
def test_result_matrix_json_uses_stable_sanitized_rows() -> None:
    body = result_matrix_json([result_entry(notes=("moto baseline",))])
    decoded = json.loads(body)

    assert decoded[0]["classification"] == "completed"
    assert decoded[0]["notes"] == ["moto baseline"]


@pytest.mark.negative
def test_result_matrix_rejects_inconsistent_rows() -> None:
    with pytest.raises(ValidationError, match="MoTo matrix rows cannot require 3DS"):
        result_entry(requires_3ds=True)

    with pytest.raises(ValidationError, match="3DS init rows must mark"):
        InitObservation(outcome=InitOutcome.THREE_DS_INITIALIZED)

    with pytest.raises(ValidationError, match="found PaymentList observations"):
        PaymentListObservation(outcome=PaymentListOutcome.FOUND)
