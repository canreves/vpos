"""Controlled ACS actions driven by OTP resolver decisions."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from paynkolay_pos.three_ds.otp_resolver import OtpResolution, OtpResolutionStatus


class SupportsAcsLocator(Protocol):
    """Small locator interface needed to fill and submit ACS forms."""

    async def fill(self, value: str) -> None:
        """Fill a form control."""

    async def click(self) -> None:
        """Click a form control."""


class AcsActionResult(BaseModel):
    """Sanitized result of an ACS action attempt."""

    model_config = {
        "extra": "forbid",
        "str_strip_whitespace": True,
        "use_enum_values": False,
    }

    submitted: bool
    reason: str = Field(min_length=1, max_length=500)
    otp_resolution: dict[str, object]


async def run_acs_otp_action(
    *,
    otp_locator: SupportsAcsLocator,
    submit_locator: SupportsAcsLocator,
    resolution: OtpResolution,
) -> AcsActionResult:
    """Fill and submit an ACS OTP form only when the resolver explicitly allows it."""

    if resolution.status is not OtpResolutionStatus.READY:
        return AcsActionResult(
            submitted=False,
            reason=f"otp_resolution_{resolution.status.value}",
            otp_resolution=resolution.evidence(),
        )

    if not resolution.should_auto_submit:
        return AcsActionResult(
            submitted=False,
            reason="otp_resolution_auto_submit_disabled",
            otp_resolution=resolution.evidence(),
        )

    otp_value = resolution.otp_value
    if otp_value is None:
        return AcsActionResult(
            submitted=False,
            reason="otp_resolution_missing_value",
            otp_resolution=resolution.evidence(),
        )

    await otp_locator.fill(otp_value)
    await submit_locator.click()
    return AcsActionResult(
        submitted=True,
        reason="otp_submitted",
        otp_resolution=resolution.evidence(),
    )
