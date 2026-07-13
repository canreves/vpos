"""Standard result matrix rows for payment-flow diagnostics."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from paynkolay_pos.config import CardBrand
from paynkolay_pos.models import PaymentStatus
from paynkolay_pos.reporting import evidence_json


class StrictDiagnosticModel(BaseModel):
    """Base model that keeps diagnostic evidence predictable."""

    model_config = {
        "extra": "forbid",
        "str_strip_whitespace": True,
        "use_enum_values": False,
    }


class ResultMatrixFlow(StrEnum):
    """High-level payment flow used by the result matrix."""

    MOTO = "moto"
    THREE_DS = "3ds"


class InitOutcome(StrEnum):
    """Outcome of the provider initialization step."""

    NOT_RUN = "not_run"
    THREE_DS_INITIALIZED = "three_ds_initialized"
    FINAL_SUCCESS = "final_success"
    FINAL_FAILED = "final_failed"
    PROVIDER_HTTP_ERROR = "provider_http_error"
    NETWORK_ERROR = "network_error"
    PARSER_ERROR = "parser_error"
    FRAMEWORK_ERROR = "framework_error"


class AcsScreenClassification(StrEnum):
    """ACS screen category before attempting OTP automation."""

    NOT_APPLICABLE = "not_applicable"
    NOT_REACHED = "not_reached"
    VISIBLE_OTP_CODE = "visible_otp_code"
    STATIC_CONFIG_OTP = "static_config_otp"
    SMS_MANUAL_REQUIRED = "sms_manual_required"
    MOBILE_APPROVAL_REQUIRED = "mobile_approval_required"
    ACS_ERROR_SCREEN = "acs_error_screen"
    BLANK_OR_REDIRECT_ERROR = "blank_or_redirect_error"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class PaymentListOutcome(StrEnum):
    """PaymentList observation for a diagnostic row."""

    NOT_QUERIED = "not_queried"
    FOUND = "found"
    MISSING = "missing"
    QUERY_ERROR = "query_error"


class OtpResolutionStatus(StrEnum):
    """Sanitized OTP resolver status for matrix reporting."""

    READY = "ready"
    MANUAL_REQUIRED = "manual_required"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"
    MISSING_SOURCE = "missing_source"


class OtpSourceType(StrEnum):
    """Sanitized OTP source type for matrix reporting."""

    VISIBLE_PAGE = "visible_page"
    STATIC_CONFIG = "static_config"


class DiagnosticClassification(StrEnum):
    """Final class used to separate provider, framework, and ACS issues."""

    COMPLETED = "completed"
    PROVIDER_FAILED = "provider_failed"
    NETWORK_ERROR = "network_error"
    FRAMEWORK_ERROR = "framework_error"
    ACS_MANUAL_REQUIRED = "acs_manual_required"
    ACS_ERROR = "acs_error"
    BLANK_OR_REDIRECT_ERROR = "blank_or_redirect_error"
    PAYMENT_LIST_MISSING = "payment_list_missing"
    PENDING_3DS = "pending_3ds"
    NEEDS_INVESTIGATION = "needs_investigation"


class InitObservation(StrictDiagnosticModel):
    """Sanitized observation from the initialize-payment step."""

    outcome: InitOutcome
    http_status: int | None = Field(default=None, ge=100, le=599)
    parsed_result_type: str | None = Field(default=None, min_length=1, max_length=120)
    provider_response_code: str | None = Field(default=None, min_length=1, max_length=32)
    provider_response_data: str | None = Field(default=None, min_length=1, max_length=240)
    bank_request_message_present: bool = False
    three_ds_form_action: str | None = Field(default=None, min_length=1, max_length=500)
    error_reason: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_3ds_observation(self) -> InitObservation:
        """Keep 3DS init evidence aligned with the observed outcome."""

        if self.outcome is InitOutcome.THREE_DS_INITIALIZED and not (
            self.bank_request_message_present
        ):
            raise ValueError("3DS init rows must mark bank_request_message_present=true")
        return self


class AcsObservation(StrictDiagnosticModel):
    """Sanitized ACS-page observation before OTP completion."""

    classification: AcsScreenClassification = AcsScreenClassification.NOT_REACHED
    page_title: str | None = Field(default=None, min_length=1, max_length=160)
    safe_url: str | None = Field(default=None, min_length=1, max_length=500)
    reason: str | None = Field(default=None, min_length=1, max_length=500)
    otp_input_found: bool = False
    submit_control_found: bool = False
    returned_to_callback: bool = False


class PaymentListObservation(StrictDiagnosticModel):
    """Sanitized PaymentList lookup observation."""

    outcome: PaymentListOutcome = PaymentListOutcome.NOT_QUERIED
    status: PaymentStatus | None = None
    provider_transaction_id_present: bool = False
    authorization_code_present: bool = False
    failure_code: str | None = Field(default=None, min_length=1, max_length=120)
    error_reason: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_status_presence(self) -> PaymentListObservation:
        """Require a status when PaymentList finds a row."""

        if self.outcome is PaymentListOutcome.FOUND and self.status is None:
            raise ValueError("found PaymentList observations must include status")
        return self


class OtpResolutionObservation(StrictDiagnosticModel):
    """Sanitized OTP resolver decision attached to a matrix row."""

    status: OtpResolutionStatus
    source_type: OtpSourceType | None = None
    otp_present: bool = False
    should_auto_submit: bool = False
    reason: str = Field(min_length=1, max_length=500)


class ResultMatrixEntry(StrictDiagnosticModel):
    """One standardized diagnostic row for a card/scenario execution."""

    card_alias: str = Field(min_length=1, max_length=120)
    brand: CardBrand
    flow: ResultMatrixFlow
    requires_3ds: bool
    scenario_id: str | None = Field(default=None, min_length=1, max_length=120)
    order_id: str | None = Field(default=None, min_length=1, max_length=120)
    init: InitObservation
    acs: AcsObservation = Field(default_factory=AcsObservation)
    otp_resolution: OtpResolutionObservation | None = None
    payment_list: PaymentListObservation = Field(default_factory=PaymentListObservation)
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_flow_consistency(self) -> ResultMatrixEntry:
        """Prevent MoTo rows from carrying 3DS-only state."""

        if self.flow is ResultMatrixFlow.MOTO and self.requires_3ds:
            raise ValueError("MoTo matrix rows cannot require 3DS")
        if (
            self.flow is ResultMatrixFlow.MOTO
            and self.acs.classification
            not in {
                AcsScreenClassification.NOT_APPLICABLE,
                AcsScreenClassification.NOT_REACHED,
            }
        ):
            raise ValueError("MoTo matrix rows cannot include ACS screen classifications")
        return self

    @property
    def classification(self) -> DiagnosticClassification:
        """Classify the row into the next actionable bucket."""

        if self.init.outcome is InitOutcome.NETWORK_ERROR:
            return DiagnosticClassification.NETWORK_ERROR

        if self.init.outcome in {InitOutcome.PARSER_ERROR, InitOutcome.FRAMEWORK_ERROR}:
            return DiagnosticClassification.FRAMEWORK_ERROR

        if self.init.outcome in {
            InitOutcome.PROVIDER_HTTP_ERROR,
            InitOutcome.FINAL_FAILED,
        }:
            return DiagnosticClassification.PROVIDER_FAILED

        if self.payment_list.outcome is PaymentListOutcome.MISSING:
            return DiagnosticClassification.PAYMENT_LIST_MISSING

        if self.payment_list.status in {
            PaymentStatus.AUTHORIZED,
            PaymentStatus.CAPTURED,
        }:
            return DiagnosticClassification.COMPLETED

        if self.payment_list.status is PaymentStatus.FAILED:
            return DiagnosticClassification.PROVIDER_FAILED

        if not self.requires_3ds:
            if self.init.outcome is InitOutcome.FINAL_SUCCESS:
                return DiagnosticClassification.COMPLETED
            return DiagnosticClassification.NEEDS_INVESTIGATION

        if self.init.outcome is not InitOutcome.THREE_DS_INITIALIZED:
            return DiagnosticClassification.NEEDS_INVESTIGATION

        if self.acs.classification in {
            AcsScreenClassification.SMS_MANUAL_REQUIRED,
            AcsScreenClassification.MOBILE_APPROVAL_REQUIRED,
        }:
            return DiagnosticClassification.ACS_MANUAL_REQUIRED

        if self.acs.classification is AcsScreenClassification.ACS_ERROR_SCREEN:
            return DiagnosticClassification.ACS_ERROR

        if self.acs.classification is AcsScreenClassification.BLANK_OR_REDIRECT_ERROR:
            return DiagnosticClassification.BLANK_OR_REDIRECT_ERROR

        if self.acs.classification in {
            AcsScreenClassification.NOT_REACHED,
            AcsScreenClassification.UNKNOWN,
            AcsScreenClassification.VISIBLE_OTP_CODE,
            AcsScreenClassification.STATIC_CONFIG_OTP,
            AcsScreenClassification.UNSUPPORTED,
        }:
            return DiagnosticClassification.PENDING_3DS

        return DiagnosticClassification.NEEDS_INVESTIGATION

    def summary_row(self) -> dict[str, object]:
        """Return the stable Result Matrix v1 column set."""

        return {
            "card_alias": self.card_alias,
            "brand": self.brand.value,
            "flow": self.flow.value,
            "requires_3ds": self.requires_3ds,
            "scenario_id": self.scenario_id,
            "order_id": self.order_id,
            "init_outcome": self.init.outcome.value,
            "init_http_status": self.init.http_status,
            "parsed_result_type": self.init.parsed_result_type,
            "provider_response_code": self.init.provider_response_code,
            "provider_response_data": self.init.provider_response_data,
            "bank_request_message_present": self.init.bank_request_message_present,
            "acs_classification": self.acs.classification.value,
            "acs_reason": self.acs.reason,
            "callback_returned": self.acs.returned_to_callback,
            "otp_resolution_status": (
                self.otp_resolution.status.value
                if self.otp_resolution is not None
                else None
            ),
            "otp_source_type": (
                self.otp_resolution.source_type.value
                if self.otp_resolution is not None
                and self.otp_resolution.source_type is not None
                else None
            ),
            "otp_present": (
                self.otp_resolution.otp_present
                if self.otp_resolution is not None
                else None
            ),
            "should_auto_submit": (
                self.otp_resolution.should_auto_submit
                if self.otp_resolution is not None
                else None
            ),
            "payment_list_outcome": self.payment_list.outcome.value,
            "payment_list_status": (
                self.payment_list.status.value if self.payment_list.status is not None else None
            ),
            "classification": self.classification.value,
            "notes": list(self.notes),
        }


def result_matrix_json(entries: tuple[ResultMatrixEntry, ...] | list[ResultMatrixEntry]) -> str:
    """Serialize result matrix rows through the standard evidence sanitizer."""

    return evidence_json([entry.summary_row() for entry in entries])
