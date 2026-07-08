"""Create a local-only Paynkolay sandbox scenario catalogue."""

from __future__ import annotations

import argparse
from pathlib import Path

from paynkolay_pos.scenarios import build_private_scenario_catalog_json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a private Paynkolay sandbox scenario catalogue.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination JSON file. Use a private path outside Git.",
    )
    parser.add_argument(
        "--card-count",
        type=int,
        default=100,
        help="Configured cards per environment. Defaults to 100.",
    )
    parser.add_argument(
        "--environment",
        choices=["dev", "uat", "test"],
        default="dev",
        help="Environment whose generated card aliases should be targeted.",
    )
    parser.add_argument(
        "--profile",
        choices=["mixed", "three_ds", "moto"],
        default="mixed",
        help="Synthetic filler card mix profile. Must match private config generation.",
    )
    args = parser.parse_args()

    body = build_private_scenario_catalog_json(
        card_count=args.card_count,
        environment=args.environment,
        profile=args.profile,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(f"{body}\n", encoding="utf-8")
    print(f"Wrote private scenario catalogue to {args.output}")
    print("Set PAYNKOLAY_SCENARIO_CATALOG to this file for sandbox readiness and runs.")


if __name__ == "__main__":
    main()
