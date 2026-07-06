"""Generate synthetic Paynkolay card datasets for private runtime configs."""

from __future__ import annotations

import argparse
from pathlib import Path

from paynkolay_pos.testing import SyntheticCardProfile, generate_synthetic_cards_json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a schema-valid synthetic Paynkolay cards JSON array.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=100,
        help="Number of synthetic cards to generate. Defaults to 100.",
    )
    parser.add_argument(
        "--profile",
        choices=[profile.value for profile in SyntheticCardProfile],
        default=SyntheticCardProfile.MIXED.value,
        help="Card mix profile. Defaults to mixed.",
    )
    parser.add_argument(
        "--alias-prefix",
        default="synthetic_card",
        help="Alias prefix used for generated card aliases.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination JSON file. Use a private path outside Git for real workflows.",
    )
    args = parser.parse_args()

    body = generate_synthetic_cards_json(
        args.count,
        alias_prefix=args.alias_prefix,
        profile=args.profile,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(f"{body}\n", encoding="utf-8")
    print(f"Wrote {args.count} synthetic cards to {args.output}")


if __name__ == "__main__":
    main()
