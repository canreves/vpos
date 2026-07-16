from __future__ import annotations

import pytest
from playwright.async_api import Page

from paynkolay_pos.diagnostics import AcsScreenClassification
from paynkolay_pos.three_ds.acs_browser import (
    SUBMIT_SELECTORS,
    _advance_garanti_sms_method_if_present,
    _visible_selector_in_frame,
)
from paynkolay_pos.three_ds.acs_profile import AcsBankProfile, AcsOtpStrategy, AcsProfile


@pytest.mark.three_ds
@pytest.mark.asyncio
async def test_submit_selector_prefers_confirmation_over_resend(browser_page: Page) -> None:
    await browser_page.set_content(
        """
        <!doctype html>
        <html>
          <body>
            <button type="submit">Resend Password</button>
            <button type="submit">Onayla</button>
          </body>
        </html>
        """,
    )

    target = await _visible_selector_in_frame(browser_page.main_frame, SUBMIT_SELECTORS)

    assert target is not None
    assert await target.locator.inner_text() == "Onayla"


@pytest.mark.three_ds
@pytest.mark.asyncio
async def test_garanti_sms_method_step_advances_to_password_input(browser_page: Page) -> None:
    await browser_page.set_content(
        """
        <!doctype html>
        <html>
          <body>
            <section id="method-step">
              <label><input type="radio" name="method" value="sms"> SMS ile doğrula</label>
              <button id="continue" type="button">Devam</button>
            </section>
            <section id="otp-step" style="display: none">
              <input id="password" type="password" name="password">
              <button type="submit">Onayla</button>
            </section>
            <script>
              document.getElementById("continue").addEventListener("click", () => {
                document.getElementById("method-step").style.display = "none";
                document.getElementById("otp-step").style.display = "block";
              });
            </script>
          </body>
        </html>
        """,
    )

    page = await _advance_garanti_sms_method_if_present(
        context=browser_page.context,
        page=browser_page,
        profile=_profile(AcsBankProfile.GARANTI),
    )

    assert page is browser_page
    assert await browser_page.locator("#password").is_visible()


@pytest.mark.three_ds
@pytest.mark.asyncio
async def test_garanti_sms_method_step_ignores_other_bank_profiles(browser_page: Page) -> None:
    await browser_page.set_content(
        """
        <!doctype html>
        <html>
          <body>
            <button id="continue" type="button">Devam</button>
            <script>
              window.clicked = false;
              document.getElementById("continue").addEventListener("click", () => {
                window.clicked = true;
              });
            </script>
          </body>
        </html>
        """,
    )

    page = await _advance_garanti_sms_method_if_present(
        context=browser_page.context,
        page=browser_page,
        profile=_profile(AcsBankProfile.AKBANK),
    )

    assert page is None
    assert await browser_page.evaluate("window.clicked") is False


def _profile(bank_profile: AcsBankProfile) -> AcsProfile:
    return AcsProfile(
        bank_profile=bank_profile,
        screen_classification=AcsScreenClassification.SMS_MANUAL_REQUIRED,
        otp_strategy=AcsOtpStrategy.SMS_MANUAL_REQUIRED,
        confidence=0.8,
        reason="test profile",
        otp_input_found=False,
        submit_control_found=True,
    )
