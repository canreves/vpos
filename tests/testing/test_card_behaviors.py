from __future__ import annotations

from paynkolay_pos.testing.card_behaviors import (
    CardAutomationStatus,
    behavior_for_alias,
    is_automatic_success_candidate,
)


def test_known_uat_card_behaviors_classify_success_and_quarantine_aliases() -> None:
    assert behavior_for_alias("akbank_visa_5232").status is CardAutomationStatus.SUCCESS_AUTO
    assert is_automatic_success_candidate("akbank_visa_5232") is True

    assert (
        behavior_for_alias("garanti_bankasi_mastercard_6017").status
        is CardAutomationStatus.AUTOMATION_DIAGNOSTIC
    )
    assert is_automatic_success_candidate("garanti_bankasi_mastercard_6017") is False

    assert behavior_for_alias("yapikredi_visa_9085").status is CardAutomationStatus.MANUAL_ONLY
    assert is_automatic_success_candidate("yapikredi_visa_9085") is False

    assert (
        behavior_for_alias("denizbank_mastercard_8608").status
        is CardAutomationStatus.QUARANTINED
    )
    assert is_automatic_success_candidate("denizbank_mastercard_8608") is False
    assert behavior_for_alias("is_bankas_troy_1396").status is CardAutomationStatus.QUARANTINED
    assert is_automatic_success_candidate("is_bankas_troy_1396") is False


def test_unknown_card_behaviors_remain_eligible_by_default() -> None:
    behavior = behavior_for_alias("new_uat_card")

    assert behavior.status is CardAutomationStatus.UNKNOWN
    assert is_automatic_success_candidate("new_uat_card") is True
