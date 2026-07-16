"""Run a guarded Paynkolay UAT parallel auto-3DS smoke through the web API."""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Sequence
from typing import Any, cast

import httpx

from paynkolay_pos.api.app import create_app
from paynkolay_pos.config import TestCard, load_runtime_settings
from paynkolay_pos.reporting import evidence_json

DEFAULT_CARD_ALIAS = "nkolay_dynamic_otp_visa_6111"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a guarded UAT parallel auto-3DS smoke via FastAPI routes.",
    )
    parser.add_argument(
        "--card-alias",
        default=DEFAULT_CARD_ALIAS,
        help=(
            "3DS card alias to run. Defaults to the known dynamic OTP Visa/QNB card; "
            "falls back to the first configured 3DS card when the default is absent."
        ),
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of repeated attempts for the selected card. Max 10.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Parallel run concurrency. Max 10.",
    )
    parser.add_argument(
        "--amount",
        default="100.00",
        help="Payment amount used for every item.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="Seconds between run status polls.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="Maximum seconds to wait for the run to finish.",
    )
    args = parser.parse_args()

    if os.getenv("PAYNKOLAY_ENABLE_LIVE_E2E") != "1":
        raise SystemExit("Set PAYNKOLAY_ENABLE_LIVE_E2E=1 before real UAT calls.")
    if args.count < 1 or args.count > 10:
        raise SystemExit("--count must be between 1 and 10.")
    if args.concurrency < 1 or args.concurrency > 10:
        raise SystemExit("--concurrency must be between 1 and 10.")

    asyncio.run(
        _run_parallel_smoke(
            requested_card_alias=args.card_alias,
            count=args.count,
            concurrency=args.concurrency,
            amount=args.amount,
            poll_interval=args.poll_interval,
            timeout=args.timeout,
        )
    )


async def _run_parallel_smoke(
    *,
    requested_card_alias: str,
    count: int,
    concurrency: int,
    amount: str,
    poll_interval: float,
    timeout: float,
) -> None:
    settings = load_runtime_settings()
    card = _select_3ds_card(settings.current.cards, requested_card_alias=requested_card_alias)
    print(
        evidence_json(
            {
                "event": "uat_parallel_3ds_smoke_start",
                "environment": settings.current.name.value,
                "provider_base_url": settings.current.base_url,
                "callback_url": settings.current.callback_base_url,
                "requested_card_alias": requested_card_alias,
                "selected_card_alias": card.alias,
                "count": count,
                "concurrency": concurrency,
                "amount": amount,
                "auto_complete_3ds": True,
            }
        )
    )

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        timeout=timeout + 30.0,
    ) as client:
        response = await client.post(
            "/api/parallel-runs",
            json={
                "mode": "manual",
                "amount": amount,
                "currency": "TRY",
                "concurrency": concurrency,
                "auto_complete_3ds": True,
                "manual_cards": [{"alias": card.alias, "repeat_count": count}],
            },
        )
        if response.status_code != httpx.codes.ACCEPTED:
            print(
                evidence_json(
                    {
                        "event": "uat_parallel_3ds_smoke_start_failed",
                        "status_code": response.status_code,
                        "response": _safe_json(response),
                    }
                )
            )
            raise SystemExit(1)

        run = response.json()
        print(
            evidence_json(
                {
                    "event": "uat_parallel_3ds_smoke_started",
                    "run_id": run["run_id"],
                    "status": run["status"],
                    "total": run["total"],
                }
            )
        )
        final_run = await _poll_run(
            client=client,
            run_id=str(run["run_id"]),
            poll_interval=poll_interval,
            timeout=timeout,
        )

    print(evidence_json({"event": "uat_parallel_3ds_smoke_finished", "run": final_run}))
    if final_run["status"] != "completed":
        raise SystemExit(1)


async def _poll_run(
    *,
    client: httpx.AsyncClient,
    run_id: str,
    poll_interval: float,
    timeout: float,
) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout
    last_payload: dict[str, Any] | None = None
    while asyncio.get_running_loop().time() < deadline:
        response = await client.get(f"/api/parallel-runs/{run_id}")
        if response.status_code != httpx.codes.OK:
            print(
                evidence_json(
                    {
                        "event": "uat_parallel_3ds_smoke_poll_failed",
                        "run_id": run_id,
                        "status_code": response.status_code,
                        "response": _safe_json(response),
                    }
                )
            )
            raise SystemExit(1)
        payload = cast(dict[str, Any], response.json())
        last_payload = payload
        print(
            evidence_json(
                {
                    "event": "uat_parallel_3ds_smoke_progress",
                    "run_id": run_id,
                    "status": payload["status"],
                    "completed": payload["completed"],
                    "failed": payload["failed"],
                    "total": payload["total"],
                    "classifications": _classification_counts(payload),
                }
            )
        )
        if payload["status"] != "running":
            return payload
        await asyncio.sleep(poll_interval)

    print(
        evidence_json(
            {
                "event": "uat_parallel_3ds_smoke_timeout",
                "run_id": run_id,
                "last_run": last_payload,
            }
        )
    )
    raise SystemExit(1)


def _select_3ds_card(
    cards: Sequence[TestCard],
    *,
    requested_card_alias: str,
) -> TestCard:
    for card in cards:
        if card.alias == requested_card_alias:
            if not card.requires_3ds:
                raise SystemExit(f"Selected card does not require 3DS: {requested_card_alias}")
            return card
    if requested_card_alias != DEFAULT_CARD_ALIAS:
        raise SystemExit(f"3DS card alias is not configured: {requested_card_alias}")
    for card in cards:
        if card.requires_3ds:
            return card
    raise SystemExit("No configured 3DS card was found.")


def _classification_counts(run: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in run.get("items", []):
        if not isinstance(item, dict):
            continue
        classification = str(item.get("classification") or "unknown")
        counts[classification] = counts.get(classification, 0) + 1
    return counts


def _safe_json(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError:
        return response.text[:500]


if __name__ == "__main__":
    main()
