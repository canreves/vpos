"""Validate private Paynkolay sandbox inputs without running payments."""

from __future__ import annotations

import argparse
from pathlib import Path

from paynkolay_pos.config import RuntimeSettings, load_runtime_settings
from paynkolay_pos.sandbox import check_sandbox_readiness, format_readiness_report
from paynkolay_pos.scenarios import (
    load_payment_scenario_catalog,
    load_payment_scenario_catalog_from_env,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check Paynkolay sandbox config and scenario readiness.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Private runtime config JSON. Defaults to PAYNKOLAY_CONFIG_FILE.",
    )
    parser.add_argument(
        "--scenarios",
        type=Path,
        help="Private scenario catalogue JSON. Defaults to PAYNKOLAY_SCENARIO_CATALOG.",
    )
    parser.add_argument(
        "--minimum-card-count",
        type=int,
        default=100,
        help="Minimum configured card count expected for delivery readiness.",
    )
    args = parser.parse_args()

    settings = (
        RuntimeSettings.model_validate_json(args.config.read_text(encoding="utf-8"))
        if args.config is not None
        else load_runtime_settings()
    )
    catalog = (
        load_payment_scenario_catalog(args.scenarios)
        if args.scenarios is not None
        else load_payment_scenario_catalog_from_env()
    )
    report = check_sandbox_readiness(
        settings,
        catalog,
        minimum_card_count=args.minimum_card_count,
    )
    print(format_readiness_report(report))
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
