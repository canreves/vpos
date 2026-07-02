"""Browser automation helpers for 3D Secure challenge pages."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field, SecretStr


class SupportsThreeDSLocator(Protocol):
    """Locator behavior used by the 3DS challenge helper."""

    async def fill(self, value: str) -> None:
        """Fill a challenge input."""

    async def click(self) -> None:
        """Click a challenge submit control."""


class SupportsThreeDSPage(Protocol):
    """Small subset of Playwright's async Page API used by 3DS automation."""

    url: str

    async def goto(self, url: str, *, wait_until: str = "domcontentloaded") -> object:
        """Navigate to a challenge page."""

    def locator(self, selector: str) -> SupportsThreeDSLocator:
        """Find a challenge page element."""

    async def wait_for_load_state(self, state: str = "networkidle") -> None:
        """Wait for the page to finish post-submit navigation or rendering."""


class ThreeDSChallengeResult(BaseModel):
    """Sanitized evidence returned after completing a 3DS challenge."""

    redirect_url: str = Field(pattern=r"^https://", min_length=12)
    final_url: str = Field(min_length=1)
    otp_selector: str = Field(min_length=1)
    submit_selector: str = Field(min_length=1)


async def complete_three_ds_challenge(
    page: SupportsThreeDSPage,
    *,
    redirect_url: str,
    otp: SecretStr | str,
    otp_selector: str = 'input[name="otp"]',
    submit_selector: str = 'button[type="submit"]',
) -> ThreeDSChallengeResult:
    """Open a 3DS challenge page, enter the OTP, submit, and return safe evidence."""

    if not redirect_url.startswith("https://"):
        raise ValueError("redirect_url must use https")
    if not otp_selector:
        raise ValueError("otp_selector must not be empty")
    if not submit_selector:
        raise ValueError("submit_selector must not be empty")

    otp_value = otp.get_secret_value() if isinstance(otp, SecretStr) else otp
    if not otp_value:
        raise ValueError("otp must not be empty")

    await page.goto(redirect_url, wait_until="domcontentloaded")
    await page.locator(otp_selector).fill(otp_value)
    await page.locator(submit_selector).click()
    await page.wait_for_load_state("networkidle")

    return ThreeDSChallengeResult(
        redirect_url=redirect_url,
        final_url=page.url,
        otp_selector=otp_selector,
        submit_selector=submit_selector,
    )
