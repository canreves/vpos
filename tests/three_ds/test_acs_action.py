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
    def __init__(
        self,
        *,
        name: str = "locator",
        fill_persists_value: bool = True,
        evaluate_persists_value: bool = True,
    ) -> None:
        self.actions: list[str] = []
        self.name = name
        self.fill_persists_value = fill_persists_value
        self.evaluate_persists_value = evaluate_persists_value
        self.value = ""

    async def fill(self, value: str) -> None:
        self.actions.append(f"fill:<redacted>:{len(value)}")
        if self.fill_persists_value:
            self.value = value

    async def input_value(self) -> str:
        return self.value

    async def evaluate(self, expression: str, arg: object = None) -> object:
        self.actions.append("evaluate:set_value")
        if self.evaluate_persists_value and isinstance(arg, str):
            self.value = arg
        return None

    async def click(self) -> None:
        self.actions.append(f"click:{self.name}")


@pytest.mark.three_ds
@pytest.mark.asyncio
async def test_run_acs_otp_action_fills_and_submits_when_ready() -> None:
    otp_locator = FakeLocator(name="otp")
    submit_locator = FakeLocator(name="submit")

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
    assert otp_locator.actions == ["click:otp", "fill:<redacted>:6", "evaluate:set_value"]
    assert submit_locator.actions == ["click:submit"]
    assert result.otp_resolution["otp_present"] is True
    assert "654321" not in result.model_dump_json()


@pytest.mark.three_ds
@pytest.mark.asyncio
async def test_run_acs_otp_action_uses_js_fill_fallback_before_submit() -> None:
    otp_locator = FakeLocator(name="otp", fill_persists_value=False)
    submit_locator = FakeLocator(name="submit")

    result = await run_acs_otp_action(
        otp_locator=otp_locator,
        submit_locator=submit_locator,
        resolution=OtpResolution(
            status=OtpResolutionStatus.READY,
            source_type=OtpSourceType.STATIC_CONFIG,
            otp=SecretStr("147852"),
            should_auto_submit=True,
            reason="resolved OTP from configured test card metadata",
        ),
    )

    assert result.submitted is True
    assert result.reason == "otp_submitted"
    assert otp_locator.actions == ["click:otp", "fill:<redacted>:6", "evaluate:set_value"]
    assert submit_locator.actions == ["click:submit"]
    assert "147852" not in result.model_dump_json()


@pytest.mark.three_ds
@pytest.mark.asyncio
async def test_run_acs_otp_action_retries_fill_before_submit_when_value_stays_empty() -> None:
    otp_locator = FakeLocator(
        name="otp",
        fill_persists_value=False,
        evaluate_persists_value=False,
    )
    submit_locator = FakeLocator(name="submit")

    result = await run_acs_otp_action(
        otp_locator=otp_locator,
        submit_locator=submit_locator,
        resolution=OtpResolution(
            status=OtpResolutionStatus.READY,
            source_type=OtpSourceType.STATIC_CONFIG,
            otp=SecretStr("147852"),
            should_auto_submit=True,
            reason="resolved OTP from configured test card metadata",
        ),
    )

    assert result.submitted is True
    assert result.reason == "otp_submitted"
    assert otp_locator.actions == [
        "click:otp",
        "fill:<redacted>:6",
        "evaluate:set_value",
        "click:otp",
        "fill:<redacted>:6",
        "evaluate:set_value",
    ]
    assert submit_locator.actions == ["click:submit"]
    assert "147852" not in result.model_dump_json()


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
