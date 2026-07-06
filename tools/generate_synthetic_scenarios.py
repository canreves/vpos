"""Generate synthetic Paynkolay scenario catalogues for private scale tests."""

from __future__ import annotations

import argparse
from pathlib import Path

from paynkolay_pos.testing import (
    SyntheticScenarioProfile,
    generate_synthetic_scenario_catalog_json,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a schema-valid synthetic Paynkolay scenario catalogue.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1000,
        help="Number of synthetic scenarios to generate. Defaults to 1000.",
    )
    parser.add_argument(
        "--profile",
        choices=[profile.value for profile in SyntheticScenarioProfile],
        default=SyntheticScenarioProfile.MIXED.value,
        help="Scenario mix profile. Defaults to mixed.",
    )
    parser.add_argument(
        "--scenario-prefix",
        default="synthetic_scenario",
        help="Prefix used for generated scenario IDs.",
    )
    parser.add_argument(
        "--card-alias-prefix",
        default="synthetic_card",
        help="Prefix used to reference generated synthetic card aliases.",
    )
    parser.add_argument(
        "--card-count",
        type=int,
        default=None,
        help="Number of cards available for alias rotation. Defaults to scenario count.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination JSON file. Use a private path outside Git for real workflows.",
    )
    args = parser.parse_args()

    body = generate_synthetic_scenario_catalog_json(
        args.count,
        scenario_prefix=args.scenario_prefix,
        card_alias_prefix=args.card_alias_prefix,
        profile=args.profile,
        card_count=args.card_count,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(f"{body}\n", encoding="utf-8")
    print(f"Wrote {args.count} synthetic scenarios to {args.output}")


if __name__ == "__main__":
    main()
