"""Build local/mock scenario catalogues from ignored credential CSV files."""

from __future__ import annotations

import argparse
from pathlib import Path

from paynkolay_pos.testing import build_credential_scenario_catalog_json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build local/mock scenarios from credential CSV files.",
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
    args = parser.parse_args()

    credentials_dir = args.credentials_dir
    body = build_credential_scenario_catalog_json(
        param_cards_path=credentials_dir / "param_merchants.csv",
        paynkolay_cards_path=credentials_dir / "paynkolay_merchants.csv",
        error_codes_path=credentials_dir / "param_hata_kodlari.csv",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(f"{body}\n", encoding="utf-8")
    print(f"Wrote credential scenario catalogue to {args.output}")


if __name__ == "__main__":
    main()
