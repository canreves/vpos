"""Controlled ACS actions driven by OTP resolver decisions."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from paynkolay_pos.three_ds.otp_resolver import OtpResolution, OtpResolutionStatus


class SupportsAcsLocator(Protocol):
    """Small locator interface needed to fill and submit ACS forms."""

    async def fill(self, value: str) -> None:
        """Fill a form control."""

    async def input_value(self) -> str:
        """Return the current form control value."""

    async def evaluate(self, expression: str, arg: object = None) -> object:
        """Evaluate JavaScript against the form control."""

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

    await _fill_otp_with_best_effort_fallback(otp_locator, otp_value)
    await submit_locator.click()
    return AcsActionResult(
        submitted=True,
        reason="otp_submitted",
        otp_resolution=resolution.evidence(),
    )


async def _fill_otp_with_best_effort_fallback(locator: SupportsAcsLocator, otp_value: str) -> None:
    await _focus_locator(locator)
    await locator.fill(otp_value)
    await _set_locator_value(locator, otp_value)


async def _focus_locator(locator: SupportsAcsLocator) -> None:
    try:
        await locator.click()
    except Exception:
        return


async def _set_locator_value(locator: SupportsAcsLocator, otp_value: str) -> None:
    await locator.evaluate(
        """
        (element, value) => {
          element.focus();
          element.value = value;
          element.dispatchEvent(new Event("input", { bubbles: true }));
          element.dispatchEvent(new Event("change", { bubbles: true }));
        }
        """,
        otp_value,
    )
