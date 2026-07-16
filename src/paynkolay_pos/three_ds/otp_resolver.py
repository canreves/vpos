"""OTP source resolution for classified ACS profiles."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, SecretStr

from paynkolay_pos.three_ds.acs_profile import (
    AcsBankProfile,
    AcsOtpStrategy,
    AcsProfile,
    AcsProfileEvidence,
    visible_otp_from_evidence,
)


class OtpResolutionStatus(StrEnum):
    """Decision returned by the OTP resolver."""

    READY = "ready"
    MANUAL_REQUIRED = "manual_required"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"
    MISSING_SOURCE = "missing_source"


class OtpSourceType(StrEnum):
    """Source used for an OTP value."""

    VISIBLE_PAGE = "visible_page"
    STATIC_CONFIG = "static_config"


DYNAMIC_OTP_SENTINEL = "__from_form__"


class OtpResolution(BaseModel):
    """Resolved OTP decision without exposing the OTP in serialized evidence."""

    model_config = {
        "extra": "forbid",
        "str_strip_whitespace": True,
        "use_enum_values": False,
    }

    status: OtpResolutionStatus
    source_type: OtpSourceType | None = None
    otp: SecretStr | None = None
    should_auto_submit: bool = False
    reason: str = Field(min_length=1, max_length=500)

    @property
    def otp_value(self) -> str | None:
        """Return the secret OTP value for controlled automation code paths."""

        if self.otp is None:
            return None
        return self.otp.get_secret_value()

    def evidence(self) -> dict[str, object]:
        """Return sanitized resolver evidence for logs and reports."""

        return {
            "status": self.status.value,
            "source_type": self.source_type.value if self.source_type is not None else None,
            "otp_present": self.otp is not None,
            "should_auto_submit": self.should_auto_submit,
            "reason": self.reason,
        }


def resolve_otp_source(
    *,
    profile: AcsProfile,
    evidence: AcsProfileEvidence,
    configured_otp: SecretStr | None,
) -> OtpResolution:
    """Choose the OTP source and whether automatic submission is allowed."""

    configured_value = configured_otp.get_secret_value().strip() if configured_otp else ""
    if (
        profile.bank_profile is AcsBankProfile.GARANTI
        and profile.otp_input_found
        and profile.submit_control_found
        and configured_value
        and configured_value != DYNAMIC_OTP_SENTINEL
    ):
        return OtpResolution(
            status=OtpResolutionStatus.READY,
            source_type=OtpSourceType.STATIC_CONFIG,
            otp=configured_otp,
            should_auto_submit=True,
            reason="resolved Garanti OTP from configured test card metadata",
        )

    if profile.otp_strategy is AcsOtpStrategy.VISIBLE_PAGE_OTP:
        visible_otp = _visible_otp_from_evidence(evidence)
        if visible_otp is None:
            return OtpResolution(
                status=OtpResolutionStatus.MISSING_SOURCE,
                reason="ACS profile expected a visible OTP but no six-digit code was found",
            )
        return OtpResolution(
            status=OtpResolutionStatus.READY,
            source_type=OtpSourceType.VISIBLE_PAGE,
            otp=SecretStr(visible_otp),
            should_auto_submit=True,
            reason="resolved OTP from visible ACS simulator text",
        )

    if profile.otp_strategy is AcsOtpStrategy.STATIC_CONFIG_OTP:
        if not configured_value or configured_value == DYNAMIC_OTP_SENTINEL:
            return OtpResolution(
                status=OtpResolutionStatus.MISSING_SOURCE,
                reason="ACS profile requires a configured OTP but none was provided",
            )
        return OtpResolution(
            status=OtpResolutionStatus.READY,
            source_type=OtpSourceType.STATIC_CONFIG,
            otp=configured_otp,
            should_auto_submit=True,
            reason="resolved OTP from configured test card metadata",
        )

    if profile.otp_strategy is AcsOtpStrategy.SMS_MANUAL_REQUIRED:
        if (
            profile.otp_input_found
            and profile.submit_control_found
            and configured_value
            and configured_value != DYNAMIC_OTP_SENTINEL
        ):
            return OtpResolution(
                status=OtpResolutionStatus.READY,
                source_type=OtpSourceType.STATIC_CONFIG,
                otp=configured_otp,
                should_auto_submit=True,
                reason="resolved OTP from configured test card metadata",
            )
        return OtpResolution(
            status=OtpResolutionStatus.MANUAL_REQUIRED,
            should_auto_submit=False,
            reason=f"ACS profile requires manual completion: {profile.otp_strategy.value}",
        )

    if profile.otp_strategy is AcsOtpStrategy.MOBILE_APPROVAL_REQUIRED:
        return OtpResolution(
            status=OtpResolutionStatus.MANUAL_REQUIRED,
            should_auto_submit=False,
            reason=f"ACS profile requires manual completion: {profile.otp_strategy.value}",
        )

    if profile.otp_strategy is AcsOtpStrategy.NOT_APPLICABLE:
        return OtpResolution(
            status=OtpResolutionStatus.NOT_APPLICABLE,
            should_auto_submit=False,
            reason="ACS profile does not support or require OTP entry",
        )

    return OtpResolution(
        status=OtpResolutionStatus.UNSUPPORTED,
        should_auto_submit=False,
        reason=f"unsupported ACS OTP strategy: {profile.otp_strategy.value}",
    )


def _visible_otp_from_evidence(evidence: AcsProfileEvidence) -> str | None:
    return visible_otp_from_evidence(evidence)
