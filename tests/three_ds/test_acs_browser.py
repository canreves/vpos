from __future__ import annotations

import pytest
from playwright.async_api import Page

from paynkolay_pos.diagnostics import AcsScreenClassification
from paynkolay_pos.three_ds.acs_browser import (
    SUBMIT_SELECTORS,
    _advance_garanti_sms_method_if_present,
    _follow_acs_final_return_if_present,
    _force_submit_otp_form_if_still_present,
    _visible_selector_in_frame,
    _visible_selector_in_page_or_frames,
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
async def test_submit_selector_supports_devam_input_button(browser_page: Page) -> None:
    await browser_page.set_content(
        """
        <!doctype html>
        <html>
          <body>
            <input type="button" value="Devam" id="continue">
            <button type="button">Yardım</button>
          </body>
        </html>
        """,
    )

    target = await _visible_selector_in_frame(browser_page.main_frame, SUBMIT_SELECTORS)

    assert target is not None
    assert target.selector == 'input[type="button"][value*="Devam" i]'


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


@pytest.mark.three_ds
@pytest.mark.asyncio
async def test_force_submit_otp_form_submits_when_click_leaves_same_page(
    browser_page: Page,
) -> None:
    callback_url = "https://paynkolay.com.tr/test/callback"
    await browser_page.route(callback_url, lambda route: route.fulfill(status=200, body="callback"))
    await browser_page.set_content(
        f"""
        <!doctype html>
        <html>
          <body>
            <form method="post" action="{callback_url}">
              <input id="password" type="password" name="password" value="147852">
              <input id="continue" type="button" value="Devam">
            </form>
          </body>
        </html>
        """,
    )
    otp_target = await _visible_selector_in_page_or_frames(browser_page, ("#password",))
    submit_target = await _visible_selector_in_page_or_frames(browser_page, ("#continue",))
    assert otp_target is not None
    assert submit_target is not None

    page = await _force_submit_otp_form_if_still_present(
        context=browser_page.context,
        page=browser_page,
        otp_target=otp_target,
        submit_target=submit_target,
        before_submit_url=browser_page.url,
    )

    assert page is browser_page
    assert browser_page.url == callback_url


@pytest.mark.three_ds
@pytest.mark.asyncio
async def test_final_return_submits_callback_form(browser_page: Page) -> None:
    callback_url = "https://paynkolay.com.tr/test/callback"
    await browser_page.route(callback_url, lambda route: route.fulfill(status=200, body="callback"))
    await browser_page.set_content(
        f"""
        <!doctype html>
        <html>
          <body>
            <p>Transaction successfully authenticated.</p>
            <form method="post" action="{callback_url}">
              <input type="hidden" name="PaRes" value="secret-pares">
              <input type="hidden" name="MD" value="secret-md">
            </form>
          </body>
        </html>
        """,
    )

    page, returned = await _follow_acs_final_return_if_present(
        context=browser_page.context,
        page=browser_page,
        callback_url=callback_url,
    )

    assert page is browser_page
    assert returned is True
    assert browser_page.url == callback_url


@pytest.mark.three_ds
@pytest.mark.asyncio
async def test_final_return_clicks_merchant_return_button(browser_page: Page) -> None:
    callback_url = "https://paynkolay.com.tr/test/callback"
    await browser_page.route(callback_url, lambda route: route.fulfill(status=200, body="callback"))
    await browser_page.set_content(
        f"""
        <!doctype html>
        <html>
          <body>
            <p>İşleminiz başarıyla gerçekleşmiştir.</p>
            <button id="merchant-return" type="button">Üye işyerine dön</button>
            <script>
              document.getElementById("merchant-return").addEventListener("click", () => {{
                window.location.href = "{callback_url}";
              }});
            </script>
          </body>
        </html>
        """,
    )

    page, returned = await _follow_acs_final_return_if_present(
        context=browser_page.context,
        page=browser_page,
        callback_url=callback_url,
    )

    assert page is browser_page
    assert returned is True
    assert browser_page.url == callback_url


@pytest.mark.three_ds
@pytest.mark.asyncio
async def test_final_return_clicks_anchor_then_submits_callback_form(browser_page: Page) -> None:
    callback_url = "https://paynkolay.com.tr/test/callback"
    await browser_page.route(callback_url, lambda route: route.fulfill(status=200, body="callback"))
    await browser_page.set_content(
        f"""
        <!doctype html>
        <html>
          <body>
            <p>İşleminiz başarıyla gerçekleşmiştir.</p>
            <a id="continue" href="#">Devam</a>
            <script>
              document.getElementById("continue").addEventListener("click", event => {{
                event.preventDefault();
                const form = document.createElement("form");
                form.method = "post";
                form.action = "{callback_url}";
                const pares = document.createElement("input");
                pares.type = "hidden";
                pares.name = "PaRes";
                pares.value = "secret-pares";
                form.appendChild(pares);
                document.body.appendChild(form);
              }});
            </script>
          </body>
        </html>
        """,
    )

    page, returned = await _follow_acs_final_return_if_present(
        context=browser_page.context,
        page=browser_page,
        callback_url=callback_url,
    )

    assert page is browser_page
    assert returned is True
    assert browser_page.url == callback_url


@pytest.mark.three_ds
@pytest.mark.asyncio
async def test_final_return_ignores_non_callback_form(browser_page: Page) -> None:
    callback_url = "https://paynkolay.com.tr/test/callback"
    await browser_page.set_content(
        """
        <!doctype html>
        <html>
          <body>
            <form method="post" action="https://issuer.example.test/diagnostic">
              <input type="hidden" name="PaRes" value="secret-pares">
            </form>
          </body>
        </html>
        """,
    )

    page, returned = await _follow_acs_final_return_if_present(
        context=browser_page.context,
        page=browser_page,
        callback_url=callback_url,
    )

    assert page is browser_page
    assert returned is False
    assert browser_page.url == "about:blank"


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
