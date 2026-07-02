from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from playwright.async_api import Page
from pydantic import SecretStr

from paynkolay_pos.three_ds import SupportsThreeDSPage, complete_three_ds_challenge


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
    assert result.final_url.endswith("/3ds/result?status=authenticated")
    assert "123456" not in result.model_dump_json()
