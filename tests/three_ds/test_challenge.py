from __future__ import annotations

import pytest
from pydantic import SecretStr

from paynkolay_pos.three_ds import (
    complete_three_ds_challenge,
    complete_three_ds_html_challenge,
)


class FakeLocator:
    def __init__(self, page: FakePage, selector: str) -> None:
        self._page = page
        self._selector = selector

    async def fill(self, value: str) -> None:
        self._page.actions.append(f"fill:{self._selector}:<redacted>")
        self._page.filled_value_lengths[self._selector] = len(value)

    async def click(self) -> None:
        self._page.actions.append(f"click:{self._selector}")
        self._page.url = "https://merchant.example.test/3ds/result?status=authenticated"


class FakePage:
    def __init__(self) -> None:
        self.url = "about:blank"
        self.actions: list[str] = []
        self.filled_value_lengths: dict[str, int] = {}

    async def goto(self, url: str, *, wait_until: str = "domcontentloaded") -> object:
        self.url = url
        self.actions.append(f"goto:{url}:{wait_until}")
        return None

    async def set_content(self, html: str, *, wait_until: str = "domcontentloaded") -> None:
        self.url = "about:blank"
        self.actions.append(f"set_content:{len(html)}:{wait_until}")

    def locator(self, selector: str) -> FakeLocator:
        self.actions.append(f"locator:{selector}")
        return FakeLocator(self, selector)

    async def wait_for_load_state(self, state: str = "networkidle") -> None:
        self.actions.append(f"wait_for_load_state:{state}")


@pytest.mark.three_ds
@pytest.mark.asyncio
async def test_complete_three_ds_challenge_enters_otp_and_returns_sanitized_result() -> None:
    page = FakePage()

    result = await complete_three_ds_challenge(
        page,
        redirect_url="https://acs.example.test/challenge/order-1001",
        otp=SecretStr("123456"),
    )

    assert page.actions == [
        "goto:https://acs.example.test/challenge/order-1001:domcontentloaded",
        'locator:input[name="otp"]',
        'fill:input[name="otp"]:<redacted>',
        'locator:button[type="submit"]',
        'click:button[type="submit"]',
        "wait_for_load_state:networkidle",
    ]
    assert result.redirect_url == "https://acs.example.test/challenge/order-1001"
    assert result.final_url == "https://merchant.example.test/3ds/result?status=authenticated"
    assert result.otp_selector == 'input[name="otp"]'
    assert result.submit_selector == 'button[type="submit"]'
    assert page.filled_value_lengths == {'input[name="otp"]': 6}
    assert "123456" not in result.model_dump_json()


@pytest.mark.three_ds
@pytest.mark.asyncio
async def test_complete_three_ds_challenge_supports_provider_specific_selectors() -> None:
    page = FakePage()

    result = await complete_three_ds_challenge(
        page,
        redirect_url="https://acs.example.test/challenge/order-1001",
        otp="654321",
        otp_selector="#password",
        submit_selector="#submit-authentication",
    )

    assert page.actions == [
        "goto:https://acs.example.test/challenge/order-1001:domcontentloaded",
        "locator:#password",
        "fill:#password:<redacted>",
        "locator:#submit-authentication",
        "click:#submit-authentication",
        "wait_for_load_state:networkidle",
    ]
    assert result.otp_selector == "#password"
    assert result.submit_selector == "#submit-authentication"
    assert page.filled_value_lengths == {"#password": 6}


@pytest.mark.three_ds
@pytest.mark.asyncio
async def test_complete_three_ds_html_challenge_loads_inline_provider_html() -> None:
    page = FakePage()

    result = await complete_three_ds_html_challenge(
        page,
        html="<form><input id='otp'><button id='submit-authentication'>Submit</button></form>",
        otp=SecretStr("123456"),
        otp_selector="#otp",
        submit_selector="#submit-authentication",
    )

    assert page.actions == [
        "set_content:79:domcontentloaded",
        "locator:#otp",
        "fill:#otp:<redacted>",
        "locator:#submit-authentication",
        "click:#submit-authentication",
        "wait_for_load_state:networkidle",
    ]
    assert result.redirect_url == "inline://paynkolay-bank-request-message"
    assert result.final_url == "https://merchant.example.test/3ds/result?status=authenticated"
    assert "123456" not in result.model_dump_json()


@pytest.mark.three_ds
@pytest.mark.negative
@pytest.mark.asyncio
async def test_complete_three_ds_challenge_rejects_invalid_inputs() -> None:
    page = FakePage()

    with pytest.raises(ValueError, match="redirect_url must use https or file"):
        await complete_three_ds_challenge(
            page,
            redirect_url="http://acs.example.test/challenge/order-1001",
            otp="123456",
        )

    with pytest.raises(ValueError, match="otp must not be empty"):
        await complete_three_ds_challenge(
            page,
            redirect_url="https://acs.example.test/challenge/order-1001",
            otp="",
        )

    with pytest.raises(ValueError, match="otp_selector must not be empty"):
        await complete_three_ds_challenge(
            page,
            redirect_url="https://acs.example.test/challenge/order-1001",
            otp="123456",
            otp_selector="",
        )

    with pytest.raises(ValueError, match="html must not be empty"):
        await complete_three_ds_html_challenge(
            page,
            html=" ",
            otp="123456",
        )
