"""Run one guarded Paynkolay UAT payment initialization smoke test."""

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx

from paynkolay_pos.clients import PaynkolayClient
from paynkolay_pos.config import PaymentEnvironment, TestCard, load_runtime_settings
from paynkolay_pos.models import PaymentInitializeRequest
from paynkolay_pos.reporting import evidence_json
from paynkolay_pos.scenarios import (
    PaymentScenario,
    load_payment_scenario_catalog_from_env,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one guarded UAT payment initialization request.",
    )
    parser.add_argument(
        "--scenario-id",
        default=None,
        help="Scenario id to run. Defaults to the first non-3DS scenario.",
    )
    parser.add_argument(
        "--card-holder-ip",
        default="127.0.0.1",
        help="cardHolderIP value sent to Paynkolay.",
    )
    parser.add_argument(
        "--skip-payment-list",
        action="store_true",
        help="Skip PaymentList verification after initialization.",
    )
    args = parser.parse_args()

    if os.getenv("PAYNKOLAY_ENABLE_LIVE_E2E") != "1":
        raise SystemExit("Set PAYNKOLAY_ENABLE_LIVE_E2E=1 before real UAT calls.")

    asyncio.run(
        _run_smoke(
            scenario_id=args.scenario_id,
            card_holder_ip=args.card_holder_ip,
            verify_payment_list=not args.skip_payment_list,
        )
    )


async def _run_smoke(
    *,
    scenario_id: str | None,
    card_holder_ip: str,
    verify_payment_list: bool,
) -> None:
    settings = load_runtime_settings()
    environment = settings.current
    catalog = load_payment_scenario_catalog_from_env()
    scenario = (
        catalog.get(scenario_id)
        if scenario_id is not None
        else _first_non_3ds_scenario(catalog.scenarios)
    )
    card = _card_for_alias(environment, scenario.card_alias)
    order_id = f"uat-smoke-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
    request = _payment_request_for(
        environment=environment,
        scenario=scenario,
        card=card,
        order_id=order_id,
    )

    evidence: dict[str, object] = {
        "event": "uat_payment_smoke_start",
        "order_id": order_id,
        "scenario_id": scenario.scenario_id,
        "card_alias": card.alias,
        "amount": scenario.canonical_amount,
        "requires_3ds": scenario.requires_3ds,
        "callback_url": environment.callback_base_url,
        "provider_base_url": environment.base_url,
    }
    print(evidence_json(evidence))

    async with PaynkolayClient(environment, timeout=30.0) as client:
        try:
            response_payload = await client.initialize_payment_form(
                request,
                success_url=environment.callback_base_url,
                fail_url=environment.callback_base_url,
                card_holder_ip=card_holder_ip,
                merchant_customer_no=environment.merchant.merchant_id,
            )
            final_status = (
                await _query_payment_list_with_retry(client=client, order_id=order_id)
                if verify_payment_list
                else None
            )
        except httpx.HTTPStatusError as exc:
            _print_http_failure(exc)
            raise SystemExit(1) from exc
        except httpx.HTTPError as exc:
            print(evidence_json({"event": "uat_payment_smoke_http_error", "error": str(exc)}))
            raise SystemExit(1) from exc

    safe_response = _response_summary(response_payload)
    print(
        evidence_json(
            {
                "event": "uat_payment_smoke_response",
                "order_id": order_id,
                "response": safe_response,
            }
        )
    )
    if final_status is not None:
        print(
            evidence_json(
                {
                    "event": "uat_payment_smoke_payment_list_status",
                    "order_id": order_id,
                    "status": final_status.model_dump(mode="json"),
                }
            )
        )


async def _query_payment_list_with_retry(
    *,
    client: PaynkolayClient,
    order_id: str,
    attempts: int = 5,
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
                        "event": "uat_payment_smoke_payment_list_retry",
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


def _first_non_3ds_scenario(scenarios: tuple[PaymentScenario, ...]) -> PaymentScenario:
    for scenario in scenarios:
        if not scenario.requires_3ds and "synthetic_filler" not in scenario.card_alias:
            return scenario
    for scenario in scenarios:
        if not scenario.requires_3ds:
            return scenario
    return scenarios[0]


def _card_for_alias(environment: PaymentEnvironment, alias: str) -> TestCard:
    for card in environment.cards:
        if card.alias == alias:
            return card
    raise LookupError(f"card alias not configured: {alias}")


def _payment_request_for(
    *,
    environment: PaymentEnvironment,
    scenario: PaymentScenario,
    card: TestCard,
    order_id: str,
) -> PaymentInitializeRequest:
    return PaymentInitializeRequest.model_validate(
        scenario.payment_request_payload(
            merchant_id=environment.merchant.merchant_id,
            terminal_id=environment.merchant.terminal_id,
            callback_url=environment.callback_base_url,
            card={
                "brand": card.brand.value,
                "pan": card.pan.get_secret_value(),
                "expiry_month": card.expiry_month,
                "expiry_year": card.expiry_year,
                "cvv": card.cvv.get_secret_value(),
            },
            order_id=order_id,
            correlation_id=f"uat-smoke-{uuid4().hex}",
        )
    )


def _response_summary(response_payload: dict[str, Any]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for key, value in response_payload.items():
        if key == "BANK_REQUEST_MESSAGE":
            summary[key] = f"<html length={len(str(value))}>"
        else:
            summary[key] = value
    return summary


def _print_http_failure(exc: httpx.HTTPStatusError) -> None:
    response = exc.response
    print(
        evidence_json(
            {
                "event": "uat_payment_smoke_http_status_error",
                "status_code": response.status_code,
                "response_text_prefix": response.text[:500],
            }
        )
    )


if __name__ == "__main__":
    main()
