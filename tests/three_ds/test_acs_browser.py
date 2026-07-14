from __future__ import annotations

import pytest
from playwright.async_api import Page

from paynkolay_pos.three_ds.acs_browser import SUBMIT_SELECTORS, _visible_selector_in_frame


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
