"""Helpers for producing sanitized payment evidence for reports."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol, cast

from pydantic import BaseModel, SecretStr

REDACTED_VALUE = "<redacted>"

_PAN_KEYS = frozenset({"pan", "card_number", "cardnumber"})
_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "cancel_refund_api_key",
        "cvc",
        "cvv",
        "hashdata",
        "hashdatav2",
        "otp",
        "password",
        "secret",
        "secret_key",
        "signature",
        "sx",
        "token",
    }
)


class _AllureLike(Protocol):
    attachment_type: Any

    def attach(self, body: str, *, name: str, attachment_type: Any) -> None:
        """Attach text evidence to a report."""


def _normalized_key(key: object) -> str:
    return str(key).strip().lower().replace("-", "_")


def mask_pan(value: object) -> str:
    """Return a PAN-safe masked value that never exposes the full card number."""

    text = str(value).strip()
    digits = "".join(character for character in text if character.isdigit())
    if len(digits) < 4:
        return REDACTED_VALUE
    return f"{'*' * max(len(digits) - 4, 0)}{digits[-4:]}"


def sanitize_evidence(value: object) -> object:
    """Recursively remove secrets and cardholder data from report evidence."""

    if isinstance(value, SecretStr):
        return REDACTED_VALUE
    if isinstance(value, BaseModel):
        return sanitize_evidence(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            key_text = str(key)
            normalized_key = _normalized_key(key)
            if normalized_key in _PAN_KEYS:
                sanitized[key_text] = mask_pan(item)
            elif normalized_key in _SENSITIVE_KEYS:
                sanitized[key_text] = REDACTED_VALUE
            else:
                sanitized[key_text] = sanitize_evidence(item)
        return sanitized
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [sanitize_evidence(item) for item in value]
    return value


def evidence_json(value: object) -> str:
    """Serialize sanitized evidence as deterministic pretty JSON."""

    return json.dumps(
        sanitize_evidence(value),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def attach_json_evidence(
    name: str,
    value: object,
    *,
    allure_module: object | None = None,
) -> str:
    """Attach sanitized JSON evidence to Allure and return the attached body."""

    body = evidence_json(value)
    allure = _resolve_allure(allure_module)
    allure.attach(
        body,
        name=name,
        attachment_type=allure.attachment_type.JSON,
    )
    return body


def _resolve_allure(allure_module: object | None) -> _AllureLike:
    if allure_module is None:
        import allure as imported_allure

        return cast(_AllureLike, imported_allure)
    return cast(_AllureLike, allure_module)
