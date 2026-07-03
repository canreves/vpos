from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from playwright.async_api import Page
from pydantic import SecretStr

from paynkolay_pos.three_ds import (
    SupportsThreeDSPage,
    complete_three_ds_challenge,
    complete_three_ds_html_challenge,
)


@pytest.mark.three_ds
@pytest.mark.asyncio
async def test_complete_three_ds_challenge_with_real_playwright_page(browser_page: Page) -> None:
    challenge_path = Path(__file__).parents[1] / "fixtures" / "three_ds" / "challenge_success.html"
    redirect_url = challenge_path.resolve().as_uri()

    result = await complete_three_ds_challenge(
        cast(SupportsThreeDSPage, browser_page),
        redirect_url=redirect_url,
        otp=SecretStr("123456"),
        otp_selector="#otp",
        submit_selector="#submit-authentication",
    )

    assert result.redirect_url == redirect_url
    assert result.final_url.endswith("#/3ds/result?status=authenticated")
    assert "123456" not in result.model_dump_json()


@pytest.mark.three_ds
@pytest.mark.asyncio
async def test_complete_three_ds_html_challenge_with_real_playwright_page(
    browser_page: Page,
) -> None:
    html = """
    <!doctype html>
    <html lang="en">
      <body>
        <form id="challenge-form">
          <input id="otp" name="otp">
          <button id="submit-authentication" type="submit">Submit</button>
        </form>
        <script>
          document.getElementById("challenge-form").addEventListener("submit", (event) => {
            event.preventDefault();
            const otp = document.getElementById("otp").value;
            const status = otp === "123456" ? "authenticated" : "failed";
            window.location.hash = `/3ds/result?status=${status}`;
          });
        </script>
      </body>
    </html>
    """

    result = await complete_three_ds_html_challenge(
        cast(SupportsThreeDSPage, browser_page),
        html=html,
        otp=SecretStr("123456"),
        otp_selector="#otp",
        submit_selector="#submit-authentication",
    )

    assert result.redirect_url == "inline://paynkolay-bank-request-message"
    assert result.final_url.endswith("#/3ds/result?status=authenticated")
    assert "123456" not in result.model_dump_json()
