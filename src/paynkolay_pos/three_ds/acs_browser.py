"""Playwright-backed ACS browser automation for 3D Secure test flows."""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import Browser, BrowserContext, Frame, Locator, Page, async_playwright
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from pydantic import BaseModel, Field, SecretStr

from paynkolay_pos.config import CardBrand
from paynkolay_pos.three_ds.acs_action import run_acs_otp_action
from paynkolay_pos.three_ds.acs_profile import (
    AcsBankProfile,
    AcsFieldEvidence,
    AcsFrameEvidence,
    AcsProfile,
    AcsProfileEvidence,
    detect_acs_profile,
)
from paynkolay_pos.three_ds.form_renderer import render_three_ds_form
from paynkolay_pos.three_ds.otp_resolver import resolve_otp_source

OTP_SELECTORS = (
    'input[name="otp"]',
    'input[name="OTP"]',
    'input[name*="otp" i]',
    'input[id*="otp" i]',
    'input[name*="sifre" i]',
    'input[id*="sifre" i]',
    'input[name*="password" i]',
    'input[id*="password" i]',
    'input[name*="pass" i]',
    'input[id*="pass" i]',
    'input[type="password"]',
    'input[type="tel"]',
    'input[type="text"]',
    'input[type="number"]',
)
SUBMIT_SELECTORS = (
    'button:has-text("Onay")',
    'button:has-text("Tamam")',
    'button:has-text("Gönder")',
    'button:has-text("Submit")',
    'input[type="submit"][value*="Onay" i]',
    'input[type="submit"][value*="Tamam" i]',
    'input[type="submit"][value*="Gönder" i]',
    'input[type="submit"][value*="Submit" i]',
    'button[type="submit"]',
    'input[type="submit"]',
    "button",
)
GARANTI_SMS_METHOD_SELECTORS = (
    'label:has-text("SMS")',
    'button:has-text("SMS")',
    'input[value*="SMS" i]',
    'input[id*="sms" i]',
    'input[name*="sms" i]',
)
GARANTI_CONTINUE_SELECTORS = (
    'button:has-text("Devam")',
    'button:has-text("Continue")',
    'input[type="submit"][value*="Devam" i]',
    'input[type="submit"][value*="Continue" i]',
    'button[type="submit"]',
    'input[type="submit"]',
)
DEFAULT_FORM_BASE_URL = "https://vpostest.qnb.com.tr/PayforACSSimulator/"


class AcsBrowserAutomationResult(BaseModel):
    """Sanitized result returned by ACS browser automation."""

    model_config = {
        "extra": "forbid",
        "str_strip_whitespace": True,
        "use_enum_values": False,
    }

    completed: bool
    submitted: bool = False
    returned_to_callback: bool = False
    reason: str = Field(min_length=1, max_length=500)
    final_url: str | None = Field(default=None, max_length=500)
    title: str | None = Field(default=None, max_length=160)
    bank_profile: str | None = Field(default=None, max_length=80)
    screen_classification: str | None = Field(default=None, max_length=80)
    otp_strategy: str | None = Field(default=None, max_length=80)
    otp_input_found: bool = False
    submit_control_found: bool = False
    otp_selector: str | None = Field(default=None, max_length=120)
    submit_selector: str | None = Field(default=None, max_length=120)
    otp_resolution: dict[str, object] | None = None
    frames: tuple[AcsFrameEvidence, ...] = ()

    def summary(self) -> dict[str, object]:
        """Return a compact sanitized summary for API/session state."""

        resolution = self.otp_resolution or {}
        return {
            "status": "completed" if self.completed else "failed",
            "submitted": self.submitted,
            "classification": self.screen_classification,
            "reason": self.reason,
            "otp_source_type": resolution.get("source_type"),
            "otp_present": bool(resolution.get("otp_present")),
            "should_auto_submit": bool(resolution.get("should_auto_submit")),
            "final_url": self.final_url,
        }


class SelectorTarget:
    """Located visible element and owning frame."""

    def __init__(self, *, frame: Frame, selector: str, locator: Locator) -> None:
        self.frame = frame
        self.selector = selector
        self.locator = locator


async def complete_acs_browser_challenge(
    *,
    html: str,
    brand: CardBrand,
    configured_otp: SecretStr | None,
    callback_url: str,
    form_base_url: str = DEFAULT_FORM_BASE_URL,
    headed: bool = False,
    close_delay_seconds: float = 0.0,
) -> AcsBrowserAutomationResult:
    """Complete a 3DS ACS challenge when a safe OTP source can be resolved."""

    document = render_three_ds_form(html)
    async with async_playwright() as playwright:
        browser: Browser | None = None
        context: BrowserContext | None = None
        try:
            browser = await playwright.chromium.launch(headless=not headed)
            context = await browser.new_context(ignore_https_errors=True)
            page = await context.new_page()
            await page.set_content(
                _html_with_base_url(document.html, form_base_url=form_base_url),
                wait_until="domcontentloaded",
            )
            if not _has_auto_submit(document.html):
                await _submit_gateway_form_if_present(page)
            await _wait_for_network_quiet(page)

            if _same_origin_path(page.url, callback_url):
                evidence = await _profile_evidence_for_page(page, brand=brand)
                profile = detect_acs_profile(evidence)
                return _result(
                    completed=True,
                    submitted=False,
                    returned_to_callback=True,
                    reason="returned_to_callback_without_otp",
                    evidence=evidence,
                    profile=profile,
                )

            evidence = await _profile_evidence_for_page(page, brand=brand)
            profile = detect_acs_profile(evidence)
            otp_target = await _visible_selector_in_page_or_frames(page, OTP_SELECTORS)
            if otp_target is None:
                advanced_page = await _advance_garanti_sms_method_if_present(
                    context=context,
                    page=page,
                    profile=profile,
                )
                if advanced_page is not None:
                    page = advanced_page
                    evidence = await _profile_evidence_for_page(page, brand=brand)
                    profile = detect_acs_profile(evidence)
                    otp_target = await _visible_selector_in_page_or_frames(page, OTP_SELECTORS)
            if otp_target is None:
                return _result(
                    completed=False,
                    submitted=False,
                    reason="otp_selector_not_found",
                    evidence=evidence,
                    profile=profile,
                )

            submit_target = await _visible_selector_in_frame(otp_target.frame, SUBMIT_SELECTORS)
            if submit_target is None:
                return _result(
                    completed=False,
                    submitted=False,
                    reason="submit_selector_not_found",
                    evidence=evidence,
                    profile=profile,
                    otp_selector=otp_target.selector,
                )

            resolution = resolve_otp_source(
                profile=profile,
                evidence=evidence,
                configured_otp=configured_otp,
            )
            action = await run_acs_otp_action(
                otp_locator=otp_target.locator,
                submit_locator=submit_target.locator,
                resolution=resolution,
            )
            if not action.submitted:
                return _result(
                    completed=False,
                    submitted=False,
                    reason=action.reason,
                    evidence=evidence,
                    profile=profile,
                    otp_selector=otp_target.selector,
                    submit_selector=submit_target.selector,
                    otp_resolution=action.otp_resolution,
                )

            await _wait_for_network_quiet(page)
            final_evidence = await _profile_evidence_for_page(page, brand=brand)
            if headed and close_delay_seconds > 0:
                await asyncio.sleep(close_delay_seconds)
            return _result(
                completed=True,
                submitted=True,
                returned_to_callback=_same_origin_path(page.url, callback_url),
                reason="otp_submitted",
                evidence=final_evidence,
                profile=profile,
                otp_selector=otp_target.selector,
                submit_selector=submit_target.selector,
                otp_resolution=action.otp_resolution,
            )
        except PlaywrightError as exc:
            return AcsBrowserAutomationResult(
                completed=False,
                submitted=False,
                reason=f"playwright_error: {exc}"[:500],
                final_url=None,
                title=None,
                otp_resolution=None,
                frames=(),
            )
        except (TypeError, ValueError) as exc:
            return AcsBrowserAutomationResult(
                completed=False,
                submitted=False,
                reason=f"framework_error: {exc}"[:500],
                frames=(),
            )
        finally:
            if context is not None:
                await context.close()
            if browser is not None:
                await browser.close()


def _result(
    *,
    completed: bool,
    submitted: bool,
    reason: str,
    evidence: AcsProfileEvidence,
    profile: AcsProfile,
    returned_to_callback: bool = False,
    otp_selector: str | None = None,
    submit_selector: str | None = None,
    otp_resolution: dict[str, object] | None = None,
) -> AcsBrowserAutomationResult:
    return AcsBrowserAutomationResult(
        completed=completed,
        submitted=submitted,
        returned_to_callback=returned_to_callback,
        reason=reason,
        final_url=evidence.final_url,
        title=evidence.title,
        bank_profile=profile.bank_profile.value,
        screen_classification=profile.screen_classification.value,
        otp_strategy=profile.otp_strategy.value,
        otp_input_found=profile.otp_input_found,
        submit_control_found=profile.submit_control_found,
        otp_selector=otp_selector,
        submit_selector=submit_selector,
        otp_resolution=otp_resolution,
        frames=evidence.frames,
    )


async def _submit_gateway_form_if_present(page: Page) -> None:
    form_count = await page.locator("form").count()
    if form_count == 0:
        return
    await page.locator("form").first.evaluate("form => form.submit()")


async def _advance_garanti_sms_method_if_present(
    *,
    context: BrowserContext,
    page: Page,
    profile: AcsProfile,
) -> Page | None:
    if profile.bank_profile is not AcsBankProfile.GARANTI:
        return None

    sms_target = await _visible_selector_in_page_or_frames(page, GARANTI_SMS_METHOD_SELECTORS)
    if sms_target is not None:
        try:
            await sms_target.locator.click()
        except PlaywrightError:
            return None

    continue_target = await _visible_selector_in_page_or_frames(page, GARANTI_CONTINUE_SELECTORS)
    if continue_target is None:
        return page

    return await _click_and_follow_page(
        context=context,
        page=page,
        locator=continue_target.locator,
    )


async def _click_and_follow_page(
    *,
    context: BrowserContext,
    page: Page,
    locator: Locator,
) -> Page:
    try:
        async with context.expect_page(timeout=3_000) as page_info:
            await locator.click()
        opened_page = await page_info.value
        await opened_page.bring_to_front()
        await _wait_for_network_quiet(opened_page)
        return opened_page
    except PlaywrightTimeoutError:
        await _wait_for_network_quiet(page)
        return page


async def _wait_for_network_quiet(page: Page) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=15_000)
    except PlaywrightTimeoutError:
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5_000)
        except PlaywrightTimeoutError:
            return


async def _visible_selector_in_page_or_frames(
    page: Page,
    selectors: tuple[str, ...],
) -> SelectorTarget | None:
    for frame in page.frames:
        target = await _visible_selector_in_frame(frame, selectors)
        if target is not None:
            return target
    return None


async def _visible_selector_in_frame(
    frame: Frame,
    selectors: tuple[str, ...],
) -> SelectorTarget | None:
    for selector in selectors:
        locator = frame.locator(selector).first
        try:
            if await locator.count() > 0 and await locator.is_visible(timeout=1_000):
                return SelectorTarget(frame=frame, selector=selector, locator=locator)
        except PlaywrightError:
            continue
    return None


async def _profile_evidence_for_page(page: Page, *, brand: CardBrand) -> AcsProfileEvidence:
    frames: list[AcsFrameEvidence] = []
    for frame in page.frames[:10]:
        frames.append(
            AcsFrameEvidence(
                url=_safe_url(frame.url),
                text_prefix=await _frame_text_prefix(frame),
                visible_fields=tuple(await _visible_field_metadata_for_frame(frame)),
            )
        )
    return AcsProfileEvidence(
        brand=brand,
        title=await page.title(),
        final_url=_safe_url(page.url),
        frames=tuple(frames),
    )


async def _frame_text_prefix(frame: Frame) -> str:
    try:
        text = await frame.locator("body").inner_text(timeout=1_000)
    except PlaywrightError:
        return ""
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)[:1000]


async def _visible_field_metadata_for_frame(frame: Frame) -> list[AcsFieldEvidence]:
    fields: list[AcsFieldEvidence] = []
    locators = frame.locator("input, button, select")
    count = min(await locators.count(), 20)
    for index in range(count):
        locator = locators.nth(index)
        try:
            if not await locator.is_visible(timeout=500):
                continue
            fields.append(
                AcsFieldEvidence(
                    tag=await locator.evaluate("el => el.tagName.toLowerCase()"),
                    type=await locator.get_attribute("type"),
                    name=await locator.get_attribute("name"),
                    id=await locator.get_attribute("id"),
                    text=(await locator.inner_text(timeout=500))[:40],
                )
            )
        except PlaywrightError:
            continue
    return fields


def _safe_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _same_origin_path(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    left_parts = urlsplit(left)
    right_parts = urlsplit(right)
    return (
        left_parts.scheme == right_parts.scheme
        and left_parts.netloc == right_parts.netloc
        and left_parts.path.rstrip("/") == right_parts.path.rstrip("/")
    )


def _html_with_base_url(html: str, *, form_base_url: str) -> str:
    if not form_base_url.strip() or "<base" in html.lower():
        return html
    if 'action="./' not in html and "action='./" not in html:
        return html
    base_tag = f'<base href="{form_base_url.rstrip("/")}/">'
    lowered = html.lower()
    head_index = lowered.find("<head>")
    if head_index >= 0:
        insert_at = head_index + len("<head>")
        return f"{html[:insert_at]}{base_tag}{html[insert_at:]}"
    return f"<head>{base_tag}</head>{html}"


def _has_auto_submit(html: str) -> bool:
    lowered = html.lower()
    return "onload" in lowered and ".submit(" in lowered
