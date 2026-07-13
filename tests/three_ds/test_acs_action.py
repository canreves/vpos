from __future__ import annotations

import pytest
from pydantic import SecretStr

from paynkolay_pos.three_ds import (
    OtpResolution,
    OtpResolutionStatus,
    OtpSourceType,
    run_acs_otp_action,
)


class FakeLocator:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def fill(self, value: str) -> None:
        self.actions.append(f"fill:<redacted>:{len(value)}")

    async def click(self) -> None:
        self.actions.append("click")


@pytest.mark.three_ds
@pytest.mark.asyncio
async def test_run_acs_otp_action_fills_and_submits_when_ready() -> None:
    otp_locator = FakeLocator()
    submit_locator = FakeLocator()

    result = await run_acs_otp_action(
        otp_locator=otp_locator,
        submit_locator=submit_locator,
        resolution=OtpResolution(
            status=OtpResolutionStatus.READY,
            source_type=OtpSourceType.STATIC_CONFIG,
            otp=SecretStr("654321"),
            should_auto_submit=True,
            reason="resolved OTP from configured test card metadata",
        ),
    )

    assert result.submitted is True
    assert result.reason == "otp_submitted"
    assert otp_locator.actions == ["fill:<redacted>:6"]
    assert submit_locator.actions == ["click"]
    assert result.otp_resolution["otp_present"] is True
    assert "654321" not in result.model_dump_json()


@pytest.mark.three_ds
@pytest.mark.asyncio
async def test_run_acs_otp_action_does_not_submit_manual_required_resolution() -> None:
    otp_locator = FakeLocator()
    submit_locator = FakeLocator()

    result = await run_acs_otp_action(
        otp_locator=otp_locator,
        submit_locator=submit_locator,
        resolution=OtpResolution(
            status=OtpResolutionStatus.MANUAL_REQUIRED,
            should_auto_submit=False,
            reason="SMS required",
        ),
    )

    assert result.submitted is False
    assert result.reason == "otp_resolution_manual_required"
    assert otp_locator.actions == []
    assert submit_locator.actions == []


@pytest.mark.three_ds
@pytest.mark.asyncio
async def test_run_acs_otp_action_does_not_submit_when_auto_submit_disabled() -> None:
    otp_locator = FakeLocator()
    submit_locator = FakeLocator()

    result = await run_acs_otp_action(
        otp_locator=otp_locator,
        submit_locator=submit_locator,
        resolution=OtpResolution(
            status=OtpResolutionStatus.READY,
            source_type=OtpSourceType.VISIBLE_PAGE,
            otp=SecretStr("123456"),
            should_auto_submit=False,
            reason="resolved but disabled",
        ),
    )

    assert result.submitted is False
    assert result.reason == "otp_resolution_auto_submit_disabled"
    assert otp_locator.actions == []
    assert submit_locator.actions == []
