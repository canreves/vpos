"""3D Secure form rendering helpers."""

from __future__ import annotations

import base64
import binascii
from typing import Literal

from pydantic import BaseModel, Field


class ThreeDSFormPayloadError(ValueError):
    """Raised when a provider 3DS form payload cannot be rendered."""


class ThreeDSFormDocument(BaseModel):
    """HTML document produced from a provider 3DS form payload."""

    html: str = Field(min_length=1)
    source: Literal["html", "base64"]


def render_three_ds_form(payload: str) -> ThreeDSFormDocument:
    """Normalize raw or base64-encoded provider 3DS form payloads into HTML."""

    normalized = payload.strip()
    if not normalized:
        raise ThreeDSFormPayloadError("3DS form payload must not be empty")

    if _looks_like_html(normalized):
        return _validated_document(normalized, source="html")

    decoded = _decode_base64_html(normalized)
    return _validated_document(decoded.strip(), source="base64")


def _validated_document(html: str, *, source: Literal["html", "base64"]) -> ThreeDSFormDocument:
    if not _looks_like_html(html):
        raise ThreeDSFormPayloadError("3DS form payload must contain HTML")
    if "<form" not in html.lower():
        raise ThreeDSFormPayloadError("3DS HTML must include a form element")
    return ThreeDSFormDocument(html=html, source=source)


def _looks_like_html(value: str) -> bool:
    lowered = value.lstrip().lower()
    return lowered.startswith(("<!doctype html", "<html", "<form"))


def _decode_base64_html(value: str) -> str:
    candidate = value
    if candidate.lower().startswith("data:text/html;base64,"):
        candidate = candidate.split(",", 1)[1]

    compact = "".join(candidate.split())
    padded = compact + ("=" * (-len(compact) % 4))
    try:
        decoded = base64.b64decode(padded, validate=True)
    except binascii.Error as exc:
        raise ThreeDSFormPayloadError("3DS form payload is not valid base64") from exc

    try:
        return decoded.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ThreeDSFormPayloadError("3DS form payload must decode as UTF-8") from exc

