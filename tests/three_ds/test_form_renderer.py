from __future__ import annotations

import base64

import pytest

from paynkolay_pos.three_ds import ThreeDSFormPayloadError, render_three_ds_form


@pytest.mark.three_ds
def test_render_three_ds_form_accepts_raw_html_form() -> None:
    document = render_three_ds_form('<form action="https://acs.example.test"></form>')

    assert document.source == "html"
    assert document.html == '<form action="https://acs.example.test"></form>'


@pytest.mark.three_ds
def test_render_three_ds_form_decodes_base64_html_form() -> None:
    encoded = base64.b64encode(b'<form action="https://acs.example.test"></form>').decode()

    document = render_three_ds_form(encoded)

    assert document.source == "base64"
    assert document.html == '<form action="https://acs.example.test"></form>'


@pytest.mark.three_ds
def test_render_three_ds_form_decodes_data_uri_payload() -> None:
    encoded = base64.b64encode(b"<html><body><form></form></body></html>").decode()

    document = render_three_ds_form(f"data:text/html;base64,{encoded}")

    assert document.source == "base64"
    assert document.html == "<html><body><form></form></body></html>"


@pytest.mark.three_ds
@pytest.mark.parametrize(
    "payload",
    [
        "",
        "not-base64",
        base64.b64encode(b"not html").decode(),
        "<html><body>No form</body></html>",
    ],
)
def test_render_three_ds_form_rejects_invalid_payloads(payload: str) -> None:
    with pytest.raises(ThreeDSFormPayloadError):
        render_three_ds_form(payload)

