from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from playwright.async_api import (
    Browser,
    Page,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)


@pytest_asyncio.fixture
async def browser_page() -> AsyncIterator[Page]:
    """Provide a real Chromium page for opt-in 3DS browser tests."""

    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch(headless=True)
        except PlaywrightError as exc:
            pytest.skip(f"Playwright Chromium is not installed: {exc}")
        try:
            page = await browser.new_page()
            yield page
        finally:
            await browser.close()


@pytest.fixture
def browser_instance(browser_page: Page) -> Browser:
    """Expose the active browser for tests that need browser-level metadata."""

    browser = browser_page.context.browser
    if browser is None:
        pytest.fail("Playwright page is not attached to a browser")
    return browser
