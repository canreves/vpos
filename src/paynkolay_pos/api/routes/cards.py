"""Runtime test card routes for the browser payment form."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError

from paynkolay_pos.api.schemas import (
    TestCardCreateRequest,
    TestCardFormFill,
    TestCardListResponse,
)
from paynkolay_pos.config import RuntimeSettings, TestCard, load_runtime_settings
from paynkolay_pos.testing.card_behaviors import behavior_for_alias

router = APIRouter(prefix="/api/cards", tags=["cards"])
CONFIG_FILE_ENV = "PAYNKOLAY_CONFIG_FILE"


@router.get("", response_model=TestCardListResponse)
async def list_test_cards() -> TestCardListResponse:
    """Return configured test cards for local/UAT tester form-fill workflows."""

    try:
        current = load_runtime_settings().current
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"runtime payment configuration is unavailable: {exc}",
        ) from exc

    return TestCardListResponse(
        environment=current.name.value,
        cards=[
            _form_fill_from_card(card)
            for card in current.cards
        ],
    )


@router.post("", response_model=TestCardFormFill, status_code=status.HTTP_201_CREATED)
async def create_test_card(request: TestCardCreateRequest) -> TestCardFormFill:
    """Append a UI-created test card to the active runtime configuration file."""

    config_path = _runtime_config_path()
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        settings = RuntimeSettings.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"runtime payment configuration is unavailable: {exc}",
        ) from exc

    current_environment = settings.current.name.value
    if any(card.alias == request.alias for card in settings.current.cards):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"card alias already exists: {request.alias}",
        )

    card_payload = _runtime_card_payload(request)
    environment_payload = _active_environment_payload(payload, current_environment)
    cards = environment_payload.setdefault("cards", [])
    if not isinstance(cards, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="active runtime environment cards must be a list",
        )
    cards.append(card_payload)

    try:
        RuntimeSettings.model_validate(payload)
        config_path.write_text(
            f"{json.dumps(payload, indent=2, ensure_ascii=False)}\n",
            encoding="utf-8",
        )
    except (OSError, ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"card could not be saved: {exc}",
        ) from exc

    return _form_fill_from_card(TestCard.model_validate(card_payload))


def _runtime_config_path() -> Path:
    config_path_value = os.getenv(CONFIG_FILE_ENV)
    if not config_path_value:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{CONFIG_FILE_ENV} must point to a configuration JSON file",
        )
    config_path = Path(config_path_value).expanduser()
    if not config_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"configuration file does not exist: {config_path}",
        )
    return config_path


def _active_environment_payload(
    payload: object,
    current_environment: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="runtime configuration must be a JSON object",
        )
    environments = payload.get("environments")
    if not isinstance(environments, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="runtime configuration environments must be an object",
        )
    environment_payload = environments.get(current_environment)
    if not isinstance(environment_payload, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"active environment is missing from runtime config: {current_environment}",
        )
    return cast(dict[str, Any], environment_payload)


def _runtime_card_payload(request: TestCardCreateRequest) -> dict[str, object]:
    requires_3ds = request.flow_type == "secure"
    payload: dict[str, object] = {
        "alias": request.alias,
        "brand": request.brand.value,
        "pan": request.card_number.get_secret_value(),
        "expiry_month": request.expiry_month,
        "expiry_year": request.expiry_year,
        "cvv": request.cvv.get_secret_value(),
        "requires_3ds": requires_3ds,
    }
    if requires_3ds and request.expected_otp is not None:
        payload["expected_otp"] = request.expected_otp.get_secret_value()
    return payload


def _form_fill_from_card(card: TestCard) -> TestCardFormFill:
    behavior = behavior_for_alias(card.alias)
    return TestCardFormFill(
        alias=card.alias,
        brand=card.brand.value,
        flow_type="secure" if card.requires_3ds else "moto",
        card_number=card.pan.get_secret_value(),
        cvv=card.cvv.get_secret_value(),
        expiry_month=card.expiry_month,
        expiry_year=card.expiry_year,
        requires_3ds=card.requires_3ds,
        has_expected_otp=card.expected_otp is not None,
        automation_status=behavior.status.value,
        automation_reason=behavior.reason,
        diagnostic_class=behavior.diagnostic_class,
        automatic_success_candidate=behavior.eligible_for_automatic_success,
    )
