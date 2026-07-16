"""Known live UAT card automation behavior keyed by card alias."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CardAutomationStatus(StrEnum):
    """Automation eligibility for live UAT card flows."""

    SUCCESS_AUTO = "success_auto"
    AUTOMATION_DIAGNOSTIC = "automation_diagnostic"
    MANUAL_ONLY = "manual_only"
    QUARANTINED = "quarantined"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CardAutomationBehavior:
    """Safe, non-secret metadata describing observed card behavior."""

    status: CardAutomationStatus
    reason: str
    diagnostic_class: str

    @property
    def eligible_for_automatic_success(self) -> bool:
        return self.status in {
            CardAutomationStatus.SUCCESS_AUTO,
            CardAutomationStatus.UNKNOWN,
        }


DEFAULT_CARD_BEHAVIOR = CardAutomationBehavior(
    status=CardAutomationStatus.UNKNOWN,
    reason="No live UAT automation behavior has been recorded for this alias.",
    diagnostic_class="unknown",
)

KNOWN_CARD_BEHAVIORS: dict[str, CardAutomationBehavior] = {
    "nkolay_dynamic_otp_visa_6111": CardAutomationBehavior(
        status=CardAutomationStatus.SUCCESS_AUTO,
        reason="Dynamic OTP flow is stable in live UAT automation.",
        diagnostic_class="visible_otp",
    ),
    "garanti_bankasi_mastercard_6017": CardAutomationBehavior(
        status=CardAutomationStatus.AUTOMATION_DIAGNOSTIC,
        reason=(
            "Embedded password 3DS automation submits successfully, but PaymentList can remain "
            "created while the provider awaits finalization."
        ),
        diagnostic_class="awaiting_provider_finalization",
    ),
    "akbank_visa_5232": CardAutomationBehavior(
        status=CardAutomationStatus.SUCCESS_AUTO,
        reason="Playwright OTP detection completes successfully.",
        diagnostic_class="visible_otp",
    ),
    "akbank_visa_7068": CardAutomationBehavior(
        status=CardAutomationStatus.SUCCESS_AUTO,
        reason="Playwright OTP detection completes successfully.",
        diagnostic_class="visible_otp",
    ),
    "yapikredi_visa_9085": CardAutomationBehavior(
        status=CardAutomationStatus.MANUAL_ONLY,
        reason="3DS approval is delivered through a mobile app smart notification.",
        diagnostic_class="mobile_app_approval",
    ),
    "is_bankasi_troy_1396": CardAutomationBehavior(
        status=CardAutomationStatus.QUARANTINED,
        reason="Provider returns a final payment result before a successful 3DS flow.",
        diagnostic_class="provider_final_result",
    ),
    "yabanc_kart_troy_8548": CardAutomationBehavior(
        status=CardAutomationStatus.QUARANTINED,
        reason="3DS flow remains on a local blank page, indicating ACS/bank-side failure.",
        diagnostic_class="acs_blank_page",
    ),
    "garanti_bankasi_mastercard_2011": CardAutomationBehavior(
        status=CardAutomationStatus.QUARANTINED,
        reason="OTP screen opens but the bank reports that the transaction cannot be processed.",
        diagnostic_class="acs_transaction_error",
    ),
    "denizbank_mastercard_8608": CardAutomationBehavior(
        status=CardAutomationStatus.QUARANTINED,
        reason="3DS flow remains on a local blank page, indicating ACS/bank-side failure.",
        diagnostic_class="acs_blank_page",
    ),
    "vakifbank_mastercard_0656": CardAutomationBehavior(
        status=CardAutomationStatus.QUARANTINED,
        reason="OTP screen opens and immediately reports verification failure.",
        diagnostic_class="acs_verification_failed",
    ),
}


def behavior_for_alias(alias: str) -> CardAutomationBehavior:
    """Return known automation behavior for a card alias."""

    return KNOWN_CARD_BEHAVIORS.get(alias, DEFAULT_CARD_BEHAVIOR)


def is_automatic_success_candidate(alias: str) -> bool:
    """Return whether an alias may be used by automatic success smoke selection."""

    return behavior_for_alias(alias).eligible_for_automatic_success
