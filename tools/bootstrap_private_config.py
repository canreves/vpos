"""Create a local-only Paynkolay runtime config skeleton."""

from __future__ import annotations

import argparse
from pathlib import Path

from paynkolay_pos.config import build_private_runtime_config_json
from paynkolay_pos.testing import SyntheticCardProfile


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a private Paynkolay runtime config skeleton.",
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
        help="Cards per environment. Defaults to 100.",
    )
    parser.add_argument(
        "--profile",
        choices=[profile.value for profile in SyntheticCardProfile],
        default=SyntheticCardProfile.MIXED.value,
        help="Synthetic filler card mix profile. Defaults to mixed.",
    )
    args = parser.parse_args()

    body = build_private_runtime_config_json(
        card_count=args.card_count,
        profile=args.profile,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(f"{body}\n", encoding="utf-8")
    print(f"Wrote private config skeleton to {args.output}")
    print("Replace merchant credentials, callback URLs, and card values before sandbox use.")


if __name__ == "__main__":
    main()
