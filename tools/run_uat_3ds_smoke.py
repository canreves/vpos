"""Run one guarded Paynkolay UAT 3DS browser smoke test."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import httpx
from playwright.async_api import (
    Browser,
    BrowserContext,
    Frame,
    Locator,
    Page,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)
from pydantic import SecretStr

from paynkolay_pos.clients import PaynkolayClient
from paynkolay_pos.config import CardBrand, PaymentEnvironment, TestCard, load_runtime_settings
from paynkolay_pos.models import PaymentInitializeRequest
from paynkolay_pos.reporting import evidence_json
from paynkolay_pos.scenarios import PaymentScenario, load_payment_scenario_catalog_from_env

OTP_SELECTORS = (
    'input[name="otp"]',
    'input[name="OTP"]',
    'input[name*="otp" i]',
    'input[id*="otp" i]',
    'input[name*="sifre" i]',
    'input[id*="sifre" i]',
    'input[name*="password" i]',
    'input[id*="password" i]',
    'input[type="password"]',
    'input[type="tel"]',
    'input[type="text"]',
)
SUBMIT_SELECTORS = (
    'button[type="submit"]',
    'input[type="submit"]',
    'button:has-text("Onay")',
    'button:has-text("Tamam")',
    'button:has-text("Gönder")',
    'button:has-text("Submit")',
    'button',
)
OTP_FROM_FORM_SENTINEL = "__from_form__"


@dataclass(frozen=True)
class UAT3DSCardOverride:
    card: TestCard
    amount: str | None = None
    card_holder: str | None = None


class FirstFormActionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.action: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.action is not None or tag.lower() != "form":
            return
        for key, value in attrs:
            if key.lower() == "action" and value:
                self.action = value
                return


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one guarded UAT 3DS initialization and browser challenge.",
    )
    parser.add_argument(
        "--scenario-id",
        default=None,
        help="3DS scenario id to run. Defaults to the first 3DS card with OTP.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show Chromium while completing the challenge.",
    )
    parser.add_argument(
        "--card-holder-ip",
        default="127.0.0.1",
        help="cardHolderIP value sent to Paynkolay.",
    )
    parser.add_argument(
        "--card-file",
        default=os.getenv("PAYNKOLAY_UAT_3DS_CARD_FILE"),
        help="Ignored JSON file containing a one-off UAT 3DS card override.",
    )
    parser.add_argument(
        "--form-base-url",
        default=os.getenv(
            "PAYNKOLAY_UAT_3DS_FORM_BASE_URL",
            "https://vpostest.qnb.com.tr/PayforACSSimulator/",
        ),
        help="Base URL used when a provider 3DS form has a relative action.",
    )
    args = parser.parse_args()

    if os.getenv("PAYNKOLAY_ENABLE_LIVE_E2E") != "1":
        raise SystemExit("Set PAYNKOLAY_ENABLE_LIVE_E2E=1 before real UAT calls.")

    asyncio.run(
        _run_3ds_smoke(
            scenario_id=args.scenario_id,
            headed=args.headed,
            card_holder_ip=args.card_holder_ip,
            card_file=args.card_file,
            form_base_url=args.form_base_url,
        )
    )


async def _run_3ds_smoke(
    *,
    scenario_id: str | None,
    headed: bool,
    card_holder_ip: str,
    card_file: str | None,
    form_base_url: str,
) -> None:
    settings = load_runtime_settings()
    environment = settings.current
    catalog = load_payment_scenario_catalog_from_env()
    scenario = (
        catalog.get(scenario_id)
        if scenario_id is not None
        else _first_3ds_scenario(catalog.scenarios, environment)
    )
    override = _override_card_from_file(card_file) if card_file is not None else None
    card = (
        override.card
        if override is not None
        else _card_for_alias(environment, scenario.card_alias)
    )
    if not scenario.requires_3ds:
        raise SystemExit("Selected scenario must require 3DS.")
    if card.expected_otp is None:
        raise SystemExit("3DS card must define expected_otp.")

    order_id = f"uat-3ds-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
    request = _payment_request_for(
        environment=environment,
        scenario=scenario,
        card=card,
        order_id=order_id,
        amount=override.amount if override is not None else None,
        card_holder=override.card_holder if override is not None else None,
    )
    print(
        evidence_json(
            {
                "event": "uat_3ds_smoke_start",
                "order_id": order_id,
                "scenario_id": scenario.scenario_id,
                "card_alias": card.alias,
                "card_source": "override_file" if card_file is not None else "runtime_config",
                "amount": override.amount
                if override is not None and override.amount is not None
                else scenario.canonical_amount,
                "callback_url": environment.callback_base_url,
                "provider_base_url": environment.base_url,
            }
        )
    )

    async with PaynkolayClient(environment, timeout=30.0) as client:
        try:
            response_payload = await client.initialize_payment_form(
                request,
                success_url=environment.callback_base_url,
                fail_url=environment.callback_base_url,
                card_holder_ip=card_holder_ip,
                merchant_customer_no=environment.merchant.merchant_id,
            )
        except httpx.HTTPError as exc:
            print(evidence_json({"event": "uat_3ds_smoke_http_error", "error": str(exc)}))
            raise SystemExit(1) from exc

        html = str(response_payload.get("BANK_REQUEST_MESSAGE") or "")
        if not html.strip():
            print(
                evidence_json(
                    {
                        "event": "uat_3ds_smoke_missing_form",
                        "order_id": order_id,
                        "response": _response_summary(response_payload),
                    }
                )
            )
            raise SystemExit(1)

        print(
            evidence_json(
                {
                    "event": "uat_3ds_smoke_initialized",
                    "order_id": order_id,
                    "response": _response_summary(response_payload),
                    "form": _form_summary(html),
                }
            )
        )

        challenge_result = await _complete_browser_challenge(
            html=html,
            otp=card.expected_otp,
            headed=headed,
            form_base_url=form_base_url,
            callback_url=environment.callback_base_url,
        )
        print(
            evidence_json(
                {
                    "event": "uat_3ds_smoke_challenge_completed",
                    "order_id": order_id,
                    **challenge_result,
                }
            )
        )

        final_status = await _query_payment_list_with_retry(client=client, order_id=order_id)
        print(
            evidence_json(
                {
                    "event": "uat_3ds_smoke_payment_list_status",
                    "order_id": order_id,
                    "status": final_status.model_dump(mode="json"),
                }
            )
        )


async def _complete_browser_challenge(
    *,
    html: str,
    otp: SecretStr,
    headed: bool,
    form_base_url: str,
    callback_url: str,
) -> dict[str, object]:
    async with async_playwright() as playwright:
        browser: Browser | None = None
        context: BrowserContext | None = None
        try:
            browser = await playwright.chromium.launch(headless=not headed)
            context = await browser.new_context(ignore_https_errors=True)
            page = await context.new_page()
            await page.set_content(
                _html_with_base_url(html, form_base_url=form_base_url),
                wait_until="domcontentloaded",
            )
            if not _has_auto_submit(html):
                await _submit_gateway_form_if_present(page)
            await _wait_for_network_quiet(page)
            if _same_origin_path(page.url, callback_url):
                return {
                    "completed": True,
                    "returned_to_callback": True,
                    "final_url": _safe_url(page.url),
                    "title": await page.title(),
                }

            otp_target = await _visible_selector_in_page_or_frames(page, OTP_SELECTORS)
            if otp_target is None:
                return {
                    "completed": False,
                    "reason": "otp_selector_not_found",
                    "final_url": _safe_url(page.url),
                    "title": await page.title(),
                    "visible_fields": await _visible_field_metadata(page),
                    "frames": await _frame_metadata(page),
                }

            submit_target = await _visible_selector_in_frame(otp_target.frame, SUBMIT_SELECTORS)
            if submit_target is None:
                return {
                    "completed": False,
                    "reason": "submit_selector_not_found",
                    "final_url": _safe_url(page.url),
                    "title": await page.title(),
                    "otp_selector": otp_target.selector,
                    "visible_fields": await _visible_field_metadata(page),
                    "frames": await _frame_metadata(page),
                }

            otp_value = await _otp_value_for_page(page, otp)
            if otp_value is None:
                return {
                    "completed": False,
                    "reason": "otp_value_not_found_in_form",
                    "final_url": _safe_url(page.url),
                    "title": await page.title(),
                    "otp_selector": otp_target.selector,
                    "visible_fields": await _visible_field_metadata(page),
                    "frames": await _frame_metadata(page),
                }

            await otp_target.locator.fill(otp_value)
            await submit_target.locator.click()
            await _wait_for_network_quiet(page)
            return {
                "completed": True,
                "final_url": _safe_url(page.url),
                "title": await page.title(),
                "otp_selector": otp_target.selector,
                "otp_frame_url": _safe_url(otp_target.frame.url),
                "submit_selector": submit_target.selector,
                "submit_frame_url": _safe_url(submit_target.frame.url),
            }
        except PlaywrightError as exc:
            return {
                "completed": False,
                "reason": "playwright_error",
                "error": str(exc),
            }
        finally:
            if context is not None:
                await context.close()
            if browser is not None:
                await browser.close()


async def _submit_gateway_form_if_present(page: Page) -> None:
    form_count = await page.locator("form").count()
    if form_count == 0:
        return
    await page.locator("form").first.evaluate("form => form.submit()")


async def _wait_for_network_quiet(page: Page) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=15_000)
    except PlaywrightTimeoutError:
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5_000)
        except PlaywrightTimeoutError:
            return


class SelectorTarget:
    def __init__(self, *, frame: Frame, selector: str, locator: Locator) -> None:
        self.frame = frame
        self.selector = selector
        self.locator = locator


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


async def _visible_field_metadata(page: Page) -> list[dict[str, object]]:
    fields: list[dict[str, object]] = []
    locators = page.locator("input, button, select")
    count = min(await locators.count(), 20)
    for index in range(count):
        locator = locators.nth(index)
        try:
            if not await locator.is_visible(timeout=500):
                continue
            fields.append(
                {
                    "tag": await locator.evaluate("el => el.tagName.toLowerCase()"),
                    "type": await locator.get_attribute("type"),
                    "name": await locator.get_attribute("name"),
                    "id": await locator.get_attribute("id"),
                    "text": (await locator.inner_text(timeout=500))[:40],
                }
            )
        except PlaywrightError:
            continue
    return fields


async def _frame_metadata(page: Page) -> list[dict[str, object]]:
    frames: list[dict[str, object]] = []
    for frame in page.frames[:10]:
        try:
            text = await frame.locator("body").inner_text(timeout=1_000)
        except PlaywrightError:
            text = ""
        frames.append(
            {
                "url": _safe_url(frame.url),
                "visible_fields": await _visible_field_metadata_for_frame(frame),
                "text_prefix": " ".join(text.split())[:240],
            }
        )
    return frames


async def _visible_field_metadata_for_frame(frame: Frame) -> list[dict[str, object]]:
    fields: list[dict[str, object]] = []
    locators = frame.locator("input, button, select")
    count = min(await locators.count(), 20)
    for index in range(count):
        locator = locators.nth(index)
        try:
            if not await locator.is_visible(timeout=500):
                continue
            fields.append(
                {
                    "tag": await locator.evaluate("el => el.tagName.toLowerCase()"),
                    "type": await locator.get_attribute("type"),
                    "name": await locator.get_attribute("name"),
                    "id": await locator.get_attribute("id"),
                    "text": (await locator.inner_text(timeout=500))[:40],
                }
            )
        except PlaywrightError:
            continue
    return fields


async def _query_payment_list_with_retry(
    *,
    client: PaynkolayClient,
    order_id: str,
    attempts: int = 10,
    delay_seconds: float = 3.0,
) -> Any:
    today = datetime.now()
    start_date = (today - timedelta(days=1)).strftime("%d.%m.%Y")
    end_date = (today + timedelta(days=1)).strftime("%d.%m.%Y")
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await client.get_transaction_status_from_payment_list(
                order_id,
                start_date=start_date,
                end_date=end_date,
            )
        except (LookupError, RuntimeError, httpx.HTTPError) as exc:
            last_error = exc
            print(
                evidence_json(
                    {
                        "event": "uat_3ds_smoke_payment_list_retry",
                        "order_id": order_id,
                        "attempt": attempt,
                        "attempts": attempts,
                        "error": str(exc),
                    }
                )
            )
            if attempt < attempts:
                await asyncio.sleep(delay_seconds)
    assert last_error is not None
    raise last_error


def _first_3ds_scenario(
    scenarios: tuple[PaymentScenario, ...],
    environment: PaymentEnvironment,
) -> PaymentScenario:
    cards = {card.alias: card for card in environment.cards}
    for scenario in scenarios:
        card = cards.get(scenario.card_alias)
        if (
            scenario.requires_3ds
            and card is not None
            and card.expected_otp is not None
            and "wrong_otp" not in scenario.tags
            and "expired_card" not in scenario.tags
        ):
            return scenario
    raise LookupError("No 3DS scenario with expected_otp was found.")


def _card_for_alias(environment: PaymentEnvironment, alias: str) -> TestCard:
    for card in environment.cards:
        if card.alias == alias:
            return card
    raise LookupError(f"card alias not configured: {alias}")


def _override_card_from_file(card_file: str) -> UAT3DSCardOverride:
    payload = json.loads(Path(card_file).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("UAT 3DS card override file must contain a JSON object")
    amount = str(payload.pop("amount", "")).strip() or None
    card_holder = str(payload.pop("card_holder", "")).strip() or None
    payload.setdefault("alias", "uat_3ds_override")
    payload.setdefault("brand", CardBrand.VISA.value)
    payload.setdefault("requires_3ds", True)
    if "expected_otp" not in payload:
        payload["expected_otp"] = OTP_FROM_FORM_SENTINEL
    return UAT3DSCardOverride(
        card=TestCard.model_validate(payload),
        amount=amount,
        card_holder=card_holder,
    )


def _payment_request_for(
    *,
    environment: PaymentEnvironment,
    scenario: PaymentScenario,
    card: TestCard,
    order_id: str,
    amount: str | None = None,
    card_holder: str | None = None,
) -> PaymentInitializeRequest:
    payload = scenario.payment_request_payload(
        merchant_id=environment.merchant.merchant_id,
        terminal_id=environment.merchant.terminal_id,
        callback_url=environment.callback_base_url,
        card={
            "brand": card.brand.value,
            "pan": card.pan.get_secret_value(),
            "expiry_month": card.expiry_month,
            "expiry_year": card.expiry_year,
            "cvv": card.cvv.get_secret_value(),
            "card_holder": card_holder or "PAYNKOLAY TEST",
        },
        order_id=order_id,
        correlation_id=f"uat-3ds-{uuid4().hex}",
    )
    if amount is not None:
        payload["amount"] = amount
    return PaymentInitializeRequest.model_validate(payload)


def _response_summary(response_payload: dict[str, Any]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for key, value in response_payload.items():
        if key == "BANK_REQUEST_MESSAGE":
            summary[key] = f"<html length={len(str(value))}>"
        elif key in {"hashData", "hashDatav2"}:
            summary[key] = "<redacted>"
        else:
            summary[key] = value
    return summary


def _form_summary(html: str) -> dict[str, object]:
    parser = FirstFormActionParser()
    parser.feed(html)
    return {
        "html_length": len(html),
        "action": _safe_url(parser.action) if parser.action else None,
    }


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


async def _otp_value_for_page(page: Page, otp: SecretStr) -> str | None:
    configured = otp.get_secret_value()
    if configured != OTP_FROM_FORM_SENTINEL:
        return configured
    texts: list[str] = []
    for frame in page.frames:
        try:
            texts.append(await frame.locator("body").inner_text(timeout=1_000))
        except PlaywrightError:
            continue
    combined = "\n".join(texts)
    for match in re.finditer(r"(?<!\d)(\d{6})(?!\d)", combined):
        return match.group(1)
    return None


if __name__ == "__main__":
    main()
