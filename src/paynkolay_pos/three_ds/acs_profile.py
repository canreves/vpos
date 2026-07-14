"""ACS profile detection from sanitized 3DS page evidence."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from paynkolay_pos.config import CardBrand
from paynkolay_pos.diagnostics import AcsScreenClassification


class AcsBankProfile(StrEnum):
    """Known ACS issuer/bank profiles observed in UAT."""

    YAPI_KREDI = "yapi_kredi"
    GARANTI = "garanti"
    AKBANK = "akbank"
    INTER_VPOS = "inter_vpos"
    QNB_SIMULATOR = "qnb_simulator"
    UNKNOWN = "unknown"


class AcsOtpStrategy(StrEnum):
    """How OTP should be sourced for a detected ACS page."""

    VISIBLE_PAGE_OTP = "visible_page_otp"
    STATIC_CONFIG_OTP = "static_config_otp"
    SMS_MANUAL_REQUIRED = "sms_manual_required"
    MOBILE_APPROVAL_REQUIRED = "mobile_approval_required"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"


class AcsFieldEvidence(BaseModel):
    """Sanitized visible field metadata collected from a frame."""

    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    tag: str | None = Field(default=None, max_length=40)
    type: str | None = Field(default=None, max_length=80)
    name: str | None = Field(default=None, max_length=120)
    id: str | None = Field(default=None, max_length=120)
    text: str | None = Field(default=None, max_length=120)


class AcsFrameEvidence(BaseModel):
    """Sanitized frame-level evidence collected from an ACS page."""

    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    url: str | None = Field(default=None, max_length=500)
    text_prefix: str = Field(default="", max_length=1000)
    visible_fields: tuple[AcsFieldEvidence, ...] = ()


class AcsProfileEvidence(BaseModel):
    """Input evidence used by the ACS profile detector."""

    model_config = {
        "extra": "forbid",
        "str_strip_whitespace": True,
        "use_enum_values": False,
    }

    brand: CardBrand | None = None
    title: str | None = Field(default=None, max_length=160)
    final_url: str | None = Field(default=None, max_length=500)
    reason: str | None = Field(default=None, max_length=500)
    frames: tuple[AcsFrameEvidence, ...] = ()


class AcsProfile(BaseModel):
    """Detected ACS profile and recommended OTP strategy."""

    model_config = {
        "extra": "forbid",
        "str_strip_whitespace": True,
        "use_enum_values": False,
    }

    bank_profile: AcsBankProfile
    screen_classification: AcsScreenClassification
    otp_strategy: AcsOtpStrategy
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)
    otp_input_found: bool = False
    submit_control_found: bool = False


def detect_acs_profile(evidence: AcsProfileEvidence) -> AcsProfile:
    """Classify a sanitized ACS page snapshot without reading secrets or raw HTML."""

    text = _combined_text(evidence)
    url = (evidence.final_url or "").lower()
    bank_profile = _detect_bank_profile(evidence=evidence, text=text, url=url)
    otp_input_found = _has_otp_input(evidence.frames)
    submit_control_found = _has_submit_control(evidence.frames)

    if _looks_like_blank_or_redirect_error(evidence.final_url):
        return AcsProfile(
            bank_profile=bank_profile,
            screen_classification=AcsScreenClassification.BLANK_OR_REDIRECT_ERROR,
            otp_strategy=AcsOtpStrategy.UNSUPPORTED,
            confidence=0.95,
            reason="browser ended on a blank or chrome error redirect",
            otp_input_found=otp_input_found,
            submit_control_found=submit_control_found,
        )

    if _looks_like_acs_error(text):
        return AcsProfile(
            bank_profile=bank_profile,
            screen_classification=AcsScreenClassification.ACS_ERROR_SCREEN,
            otp_strategy=AcsOtpStrategy.NOT_APPLICABLE,
            confidence=0.9,
            reason="ACS page contains an error marker",
            otp_input_found=otp_input_found,
            submit_control_found=submit_control_found,
        )

    if _has_visible_otp_code(text) and otp_input_found:
        return AcsProfile(
            bank_profile=bank_profile,
            screen_classification=AcsScreenClassification.VISIBLE_OTP_CODE,
            otp_strategy=AcsOtpStrategy.VISIBLE_PAGE_OTP,
            confidence=0.8,
            reason="ACS page appears to include a visible simulator OTP",
            otp_input_found=otp_input_found,
            submit_control_found=submit_control_found,
        )

    if _looks_like_mobile_approval(text):
        return AcsProfile(
            bank_profile=bank_profile,
            screen_classification=AcsScreenClassification.MOBILE_APPROVAL_REQUIRED,
            otp_strategy=AcsOtpStrategy.MOBILE_APPROVAL_REQUIRED,
            confidence=0.85,
            reason="ACS page asks for mobile app approval",
            otp_input_found=otp_input_found,
            submit_control_found=submit_control_found,
        )

    if _looks_like_sms_challenge(text, otp_input_found):
        return AcsProfile(
            bank_profile=bank_profile,
            screen_classification=AcsScreenClassification.SMS_MANUAL_REQUIRED,
            otp_strategy=AcsOtpStrategy.SMS_MANUAL_REQUIRED,
            confidence=0.85,
            reason="ACS page asks for an SMS password/code",
            otp_input_found=otp_input_found,
            submit_control_found=submit_control_found,
        )

    if otp_input_found:
        return AcsProfile(
            bank_profile=bank_profile,
            screen_classification=AcsScreenClassification.STATIC_CONFIG_OTP,
            otp_strategy=AcsOtpStrategy.STATIC_CONFIG_OTP,
            confidence=0.65,
            reason="ACS page has an OTP-like input but no visible source marker",
            otp_input_found=True,
            submit_control_found=submit_control_found,
        )

    return AcsProfile(
        bank_profile=bank_profile,
        screen_classification=AcsScreenClassification.UNSUPPORTED,
        otp_strategy=AcsOtpStrategy.UNSUPPORTED,
        confidence=0.4,
        reason="ACS page did not match a supported profile",
        otp_input_found=False,
        submit_control_found=submit_control_found,
    )


def _detect_bank_profile(
    *,
    evidence: AcsProfileEvidence,
    text: str,
    url: str,
) -> AcsBankProfile:
    title = (evidence.title or "").lower()
    if "yapikredi" in url or "yapı kredi" in text or "yapi kredi" in text or "yapı kredi" in title:
        return AcsBankProfile.YAPI_KREDI
    if "garanti" in url or "garanti" in text or "bonus" in text:
        return AcsBankProfile.GARANTI
    if "akbank" in url or "akbank" in text:
        return AcsBankProfile.AKBANK
    if "inter-vpos" in url or "inter vpos" in text:
        return AcsBankProfile.INTER_VPOS
    if "qnb" in url or "payforacssimulator" in url:
        return AcsBankProfile.QNB_SIMULATOR
    return AcsBankProfile.UNKNOWN


def _combined_text(evidence: AcsProfileEvidence) -> str:
    parts = [evidence.title or "", evidence.reason or ""]
    parts.extend(frame.text_prefix for frame in evidence.frames)
    return " ".join(part.lower() for part in parts if part)


def _has_otp_input(frames: tuple[AcsFrameEvidence, ...]) -> bool:
    markers = ("otp", "sifre", "şifre", "pass", "password", "sms")
    for field in _fields(frames):
        field_text = " ".join(
            value.lower()
            for value in (field.id, field.name, field.type, field.text)
            if value is not None
        )
        if any(marker in field_text for marker in markers):
            return True
    return False


def _has_submit_control(frames: tuple[AcsFrameEvidence, ...]) -> bool:
    markers = ("submit", "onay", "gönder", "gonder", "tamam")
    for field in _fields(frames):
        field_text = " ".join(
            value.lower()
            for value in (field.tag, field.type, field.text, field.id, field.name)
            if value is not None
        )
        if any(marker in field_text for marker in markers):
            return True
    return False


def _fields(frames: tuple[AcsFrameEvidence, ...]) -> tuple[AcsFieldEvidence, ...]:
    fields: list[AcsFieldEvidence] = []
    for frame in frames:
        fields.extend(frame.visible_fields)
    return tuple(fields)


def _looks_like_blank_or_redirect_error(final_url: str | None) -> bool:
    if not final_url:
        return False
    lowered = final_url.lower()
    return lowered.startswith("chrome-error://") or lowered == "about:blank"


def _looks_like_acs_error(text: str) -> bool:
    markers = (
        "3d-",
        "gerçekleştiremiyoruz",
        "gerceklestiremiyoruz",
        "tekrar deneyiniz",
        "error",
        "hata",
    )
    return any(marker in text for marker in markers)


def _looks_like_mobile_approval(text: str) -> bool:
    markers = ("mobil", "mobile", "uygulama", "cep şube", "cep sube")
    return any(marker in text for marker in markers) and "sms" not in text


def _looks_like_sms_challenge(text: str, otp_input_found: bool) -> bool:
    markers = ("sms", "akıllı sms", "akilli sms", "şifre", "sifre")
    return otp_input_found and any(marker in text for marker in markers)


def _has_visible_otp_code(text: str) -> bool:
    markers = ("otp", "sifre", "şifre", "password", "code", "kod")
    if not any(marker in text for marker in markers):
        return False
    tokens = text.replace(":", " ").replace(".", " ").split()
    return any(token.isdigit() and len(token) == 6 for token in tokens)
