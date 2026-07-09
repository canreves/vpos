"""Query one guarded Paynkolay UAT transaction through PaymentList."""

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime, timedelta

import httpx

from paynkolay_pos.clients import PaynkolayClient
from paynkolay_pos.config import load_runtime_settings
from paynkolay_pos.reporting import evidence_json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query one UAT transaction through Paynkolay PaymentList.",
    )
    parser.add_argument("--order-id", required=True, help="clientRefCode/order id to query.")
    parser.add_argument("--start-date", default=None, help="DD.MM.YYYY, defaults to yesterday.")
    parser.add_argument("--end-date", default=None, help="DD.MM.YYYY, defaults to tomorrow.")
    args = parser.parse_args()

    if os.getenv("PAYNKOLAY_ENABLE_LIVE_E2E") != "1":
        raise SystemExit("Set PAYNKOLAY_ENABLE_LIVE_E2E=1 before real UAT calls.")

    today = datetime.now()
    start_date = args.start_date or (today - timedelta(days=1)).strftime("%d.%m.%Y")
    end_date = args.end_date or (today + timedelta(days=1)).strftime("%d.%m.%Y")

    asyncio.run(
        _query_payment_list(
            order_id=args.order_id,
            start_date=start_date,
            end_date=end_date,
        )
    )


async def _query_payment_list(*, order_id: str, start_date: str, end_date: str) -> None:
    settings = load_runtime_settings()
    environment = settings.current
    print(
        evidence_json(
            {
                "event": "uat_payment_list_query_start",
                "order_id": order_id,
                "start_date": start_date,
                "end_date": end_date,
                "provider_base_url": environment.base_url,
            }
        )
    )
    async with PaynkolayClient(environment, timeout=30.0) as client:
        try:
            status = await client.get_transaction_status_from_payment_list(
                order_id,
                start_date=start_date,
                end_date=end_date,
            )
        except httpx.HTTPStatusError as exc:
            print(
                evidence_json(
                    {
                        "event": "uat_payment_list_http_status_error",
                        "status_code": exc.response.status_code,
                        "response_text_prefix": exc.response.text[:500],
                    }
                )
            )
            raise SystemExit(1) from exc
        except (LookupError, RuntimeError, httpx.HTTPError) as exc:
            print(evidence_json({"event": "uat_payment_list_error", "error": str(exc)}))
            raise SystemExit(1) from exc

    print(
        evidence_json(
            {
                "event": "uat_payment_list_status",
                "order_id": order_id,
                "status": status.model_dump(mode="json"),
            }
        )
    )


if __name__ == "__main__":
    main()
