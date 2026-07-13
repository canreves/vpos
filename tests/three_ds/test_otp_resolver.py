from __future__ import annotations

import pytest
from pydantic import SecretStr

from paynkolay_pos.config import CardBrand
from paynkolay_pos.diagnostics import AcsScreenClassification
from paynkolay_pos.three_ds import (
    AcsBankProfile,
    AcsFieldEvidence,
    AcsFrameEvidence,
    AcsOtpStrategy,
    AcsProfile,
    AcsProfileEvidence,
    OtpResolutionStatus,
    OtpSourceType,
    detect_acs_profile,
    resolve_otp_source,
)


def profile(strategy: AcsOtpStrategy) -> AcsProfile:
    return AcsProfile(
        bank_profile=AcsBankProfile.UNKNOWN,
        screen_classification=AcsScreenClassification.STATIC_CONFIG_OTP,
        otp_strategy=strategy,
        confidence=0.8,
        reason="test profile",
        otp_input_found=True,
        submit_control_found=True,
    )


@pytest.mark.three_ds
def test_resolve_otp_source_uses_visible_page_otp_without_leaking_value() -> None:
    evidence = AcsProfileEvidence(
        brand=CardBrand.VISA,
        title="ACS Simulator",
        frames=(
            AcsFrameEvidence(
                text_prefix="Test OTP code: 123456",
                visible_fields=(
                    AcsFieldEvidence(tag="input", type="text", name="otp"),
                    AcsFieldEvidence(tag="button", type="submit", text="Submit"),
                ),
            ),
        ),
    )
    detected = detect_acs_profile(evidence)

    resolution = resolve_otp_source(
        profile=detected,
        evidence=evidence,
        configured_otp=None,
    )

    assert resolution.status is OtpResolutionStatus.READY
    assert resolution.source_type is OtpSourceType.VISIBLE_PAGE
    assert resolution.otp_value == "123456"
    assert resolution.should_auto_submit is True
    assert resolution.evidence()["otp_present"] is True
    assert "123456" not in str(resolution.evidence())
    assert "123456" not in resolution.model_dump_json()


@pytest.mark.three_ds
def test_resolve_otp_source_uses_static_config_otp() -> None:
    resolution = resolve_otp_source(
        profile=profile(AcsOtpStrategy.STATIC_CONFIG_OTP),
        evidence=AcsProfileEvidence(),
        configured_otp=SecretStr("654321"),
    )

    assert resolution.status is OtpResolutionStatus.READY
    assert resolution.source_type is OtpSourceType.STATIC_CONFIG
    assert resolution.otp_value == "654321"
    assert resolution.should_auto_submit is True


@pytest.mark.three_ds
def test_resolve_otp_source_blocks_sms_and_mobile_manual_profiles() -> None:
    sms = resolve_otp_source(
        profile=profile(AcsOtpStrategy.SMS_MANUAL_REQUIRED),
        evidence=AcsProfileEvidence(),
        configured_otp=SecretStr("654321"),
    )
    mobile = resolve_otp_source(
        profile=profile(AcsOtpStrategy.MOBILE_APPROVAL_REQUIRED),
        evidence=AcsProfileEvidence(),
        configured_otp=SecretStr("654321"),
    )

    assert sms.status is OtpResolutionStatus.MANUAL_REQUIRED
    assert sms.should_auto_submit is False
    assert mobile.status is OtpResolutionStatus.MANUAL_REQUIRED
    assert mobile.should_auto_submit is False


@pytest.mark.three_ds
def test_resolve_otp_source_reports_missing_source() -> None:
    static_missing = resolve_otp_source(
        profile=profile(AcsOtpStrategy.STATIC_CONFIG_OTP),
        evidence=AcsProfileEvidence(),
        configured_otp=None,
    )
    visible_missing = resolve_otp_source(
        profile=profile(AcsOtpStrategy.VISIBLE_PAGE_OTP),
        evidence=AcsProfileEvidence(),
        configured_otp=None,
    )

    assert static_missing.status is OtpResolutionStatus.MISSING_SOURCE
    assert static_missing.should_auto_submit is False
    assert visible_missing.status is OtpResolutionStatus.MISSING_SOURCE
    assert visible_missing.should_auto_submit is False


@pytest.mark.three_ds
def test_resolve_otp_source_marks_unsupported_profiles() -> None:
    resolution = resolve_otp_source(
        profile=profile(AcsOtpStrategy.UNSUPPORTED),
        evidence=AcsProfileEvidence(),
        configured_otp=SecretStr("654321"),
    )

    assert resolution.status is OtpResolutionStatus.UNSUPPORTED
    assert resolution.should_auto_submit is False
