"""Build a simple MoTo scenario catalogue from real provider CSV cards."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from paynkolay_pos.testing.real_cards import (
    build_moto_scenarios_for_cards,
    read_param_cards,
    read_paynkolay_cards,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate one MoTo scenario per real Paynkolay/Param card.",
    )
    parser.add_argument(
        "--paynkolay-csv",
        type=Path,
        required=True,
        help="Path to the Paynkolay merchants CSV.",
    )
    parser.add_argument(
        "--param-csv",
        type=Path,
        required=True,
        help="Path to the Param merchants CSV.",
    )
    parser.add_argument(
        "--amount",
        default="50.00",
        help="Amount used for every generated MoTo scenario. Defaults to 50.00.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination JSON file. Use a private path outside Git for real cards.",
    )
    args = parser.parse_args()

    cards = read_paynkolay_cards(args.paynkolay_csv) + read_param_cards(args.param_csv)
    payload = build_moto_scenarios_for_cards(cards, amount=args.amount)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    count = len(payload["scenarios"])
    print(f"Wrote {count} MoTo scenarios to {args.output}")


if __name__ == "__main__":
    main()
