"""Build a private runtime config from ignored credential CSV files."""

from __future__ import annotations

import argparse
from pathlib import Path

from paynkolay_pos.testing import build_credential_runtime_config_json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a private runtime config from credential CSV files.",
    )
    parser.add_argument(
        "--credentials-dir",
        type=Path,
        default=Path("credentials"),
        help="Directory containing ignored credential CSV files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination JSON file. Use a private path outside Git.",
    )
    parser.add_argument(
        "--environment",
        choices=["dev", "uat", "test"],
        default="dev",
        help="Environment name to generate. Defaults to dev for local/mock use.",
    )
    parser.add_argument(
        "--base-url",
        default="https://local-mock.payments.invalid",
        help="Provider base URL. For UAT use https://paynkolaytest.nkolayislem.com.tr/Vpos.",
    )
    parser.add_argument(
        "--callback-base-url",
        default="https://local-mock.callbacks.invalid",
        help="Merchant callback/result base URL.",
    )
    parser.add_argument("--merchant-id", default="local-mock-merchant")
    parser.add_argument("--terminal-id", default="local-mock-terminal")
    parser.add_argument("--api-key", default="local-mock-payment-key")
    parser.add_argument("--list-api-key", default="local-mock-list-key")
    parser.add_argument("--cancel-refund-api-key", default="local-mock-cancel-refund-key")
    parser.add_argument("--secret-key", default="local-mock-secret-key")
    args = parser.parse_args()

    credentials_dir = args.credentials_dir
    body = build_credential_runtime_config_json(
        param_cards_path=credentials_dir / "param_merchants.csv",
        paynkolay_cards_path=credentials_dir / "paynkolay_merchants.csv",
        active_environment=args.environment,
        base_url=args.base_url,
        callback_base_url=args.callback_base_url,
        merchant_id=args.merchant_id,
        terminal_id=args.terminal_id,
        api_key=args.api_key,
        list_api_key=args.list_api_key,
        cancel_refund_api_key=args.cancel_refund_api_key,
        secret_key=args.secret_key,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(f"{body}\n", encoding="utf-8")
    print(f"Wrote credential runtime config to {args.output}")


if __name__ == "__main__":
    main()
