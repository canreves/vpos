"""Build a combined card dataset: real provider cards + synthetic MoTo fillers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from paynkolay_pos.testing.real_cards import build_combined_card_dataset


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Combine real Paynkolay + Param CSV cards with synthetic fillers.",
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
        "--total-count",
        type=int,
        default=100,
        help="Total number of cards in the final dataset. Defaults to 100.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination JSON file. Use a private path outside Git for real cards.",
    )
    args = parser.parse_args()

    cards = build_combined_card_dataset(
        paynkolay_csv=args.paynkolay_csv,
        param_csv=args.param_csv,
        total_count=args.total_count,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(cards, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    real = sum(1 for c in cards if "real" in str(c["alias"]))
    print(f"Wrote {len(cards)} cards ({real} real + {len(cards) - real} synthetic) to {args.output}")


if __name__ == "__main__":
    main()
