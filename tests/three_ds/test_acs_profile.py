from __future__ import annotations

import pytest

from paynkolay_pos.config import CardBrand
from paynkolay_pos.diagnostics import AcsScreenClassification
from paynkolay_pos.three_ds import (
    AcsBankProfile,
    AcsFieldEvidence,
    AcsFrameEvidence,
    AcsOtpStrategy,
    AcsProfileEvidence,
    detect_acs_profile,
)


def frame(
    *,
    url: str = "https://uatacs.yapikredi.com.tr/TDSecure/",
    text_prefix: str,
    fields: tuple[AcsFieldEvidence, ...] = (),
) -> AcsFrameEvidence:
    return AcsFrameEvidence(url=url, text_prefix=text_prefix, visible_fields=fields)


@pytest.mark.three_ds
def test_detect_acs_profile_classifies_yapi_kredi_sms_challenge() -> None:
    profile = detect_acs_profile(
        AcsProfileEvidence(
            brand=CardBrand.VISA,
            title="Yapı Kredi",
            final_url="https://uatacs.yapikredi.com.tr/TDSecure/",
            frames=(
                frame(
                    text_prefix="Akıllı SMS Şifresi Cep Telefonu 0 555 *** 55 55",
                    fields=(
                        AcsFieldEvidence(tag="input", type="number", id="smspass"),
                        AcsFieldEvidence(tag="button", type="submit", text="Onay"),
                    ),
                ),
            ),
        )
    )

    assert profile.bank_profile is AcsBankProfile.YAPI_KREDI
    assert profile.screen_classification is AcsScreenClassification.SMS_MANUAL_REQUIRED
    assert profile.otp_strategy is AcsOtpStrategy.SMS_MANUAL_REQUIRED
    assert profile.otp_input_found is True
    assert profile.submit_control_found is True


@pytest.mark.three_ds
def test_detect_acs_profile_classifies_acs_error_screen() -> None:
    profile = detect_acs_profile(
        AcsProfileEvidence(
            brand=CardBrand.VISA,
            title="Yapı Kredi",
            final_url="https://uatacs.yapikredi.com.tr/TDSecure/",
            frames=(
                frame(
                    text_prefix=(
                        "İşleminizi şu anda gerçekleştiremiyoruz. "
                        "Lütfen daha sonra tekrar deneyiniz. (3D-102)"
                    )
                ),
            ),
        )
    )

    assert profile.bank_profile is AcsBankProfile.YAPI_KREDI
    assert profile.screen_classification is AcsScreenClassification.ACS_ERROR_SCREEN
    assert profile.otp_strategy is AcsOtpStrategy.NOT_APPLICABLE


@pytest.mark.three_ds
def test_detect_acs_profile_classifies_troy_redirect_error() -> None:
    profile = detect_acs_profile(
        AcsProfileEvidence(
            brand=CardBrand.TROY,
            title="",
            final_url="chrome-error://chromewebdata/",
            frames=(frame(url="chrome-error://chromewebdata/", text_prefix=""),),
        )
    )

    assert profile.screen_classification is AcsScreenClassification.BLANK_OR_REDIRECT_ERROR
    assert profile.otp_strategy is AcsOtpStrategy.UNSUPPORTED


@pytest.mark.three_ds
def test_detect_acs_profile_classifies_visible_simulator_otp() -> None:
    profile = detect_acs_profile(
        AcsProfileEvidence(
            brand=CardBrand.VISA,
            title="ACS Simulator",
            final_url="https://vpostest.qnb.com.tr/PayforACSSimulator/",
            frames=(
                frame(
                    url="https://vpostest.qnb.com.tr/PayforACSSimulator/",
                    text_prefix="OTP code: 123456",
                    fields=(
                        AcsFieldEvidence(tag="input", type="text", name="otp"),
                        AcsFieldEvidence(tag="button", type="submit", text="Submit"),
                    ),
                ),
            ),
        )
    )

    assert profile.bank_profile is AcsBankProfile.QNB_SIMULATOR
    assert profile.screen_classification is AcsScreenClassification.VISIBLE_OTP_CODE
    assert profile.otp_strategy is AcsOtpStrategy.VISIBLE_PAGE_OTP


@pytest.mark.three_ds
def test_detect_acs_profile_falls_back_to_static_config_otp_for_generic_input() -> None:
    profile = detect_acs_profile(
        AcsProfileEvidence(
            brand=CardBrand.MASTERCARD,
            title="Bank ACS",
            final_url="https://acs.example.test/challenge",
            frames=(
                frame(
                    url="https://acs.example.test/challenge",
                    text_prefix="Enter your authentication code",
                    fields=(
                        AcsFieldEvidence(tag="input", type="password", id="password"),
                        AcsFieldEvidence(tag="button", type="submit", text="Submit"),
                    ),
                ),
            ),
        )
    )

    assert profile.bank_profile is AcsBankProfile.UNKNOWN
    assert profile.screen_classification is AcsScreenClassification.STATIC_CONFIG_OTP
    assert profile.otp_strategy is AcsOtpStrategy.STATIC_CONFIG_OTP
