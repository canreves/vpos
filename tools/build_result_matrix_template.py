"""Build a Result Matrix v1 template from the configured scenario catalogue."""

from __future__ import annotations

import argparse

from paynkolay_pos.config import PaymentEnvironment, TestCard, load_runtime_settings
from paynkolay_pos.diagnostics import (
    AcsObservation,
    AcsScreenClassification,
    InitObservation,
    InitOutcome,
    PaymentListObservation,
    PaymentListOutcome,
    ResultMatrixEntry,
    ResultMatrixFlow,
    result_matrix_json,
)
from paynkolay_pos.scenarios import PaymentScenario, load_payment_scenario_catalog_from_env


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a sanitized diagnostic result matrix template without UAT calls.",
    )
    parser.add_argument(
        "--scenario-id",
        action="append",
        default=None,
        help="Scenario id to include. Can be passed multiple times. Defaults to all scenarios.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of template rows after filtering.",
    )
    args = parser.parse_args()

    settings = load_runtime_settings()
    environment = settings.current
    catalog = load_payment_scenario_catalog_from_env()
    scenarios = (
        tuple(catalog.get(scenario_id) for scenario_id in args.scenario_id)
        if args.scenario_id is not None
        else catalog.scenarios
    )
    if args.limit is not None:
        scenarios = scenarios[: args.limit]

    entries = tuple(
        _template_entry(environment=environment, scenario=scenario)
        for scenario in scenarios
    )
    print(result_matrix_json(entries))


def _template_entry(
    *,
    environment: PaymentEnvironment,
    scenario: PaymentScenario,
) -> ResultMatrixEntry:
    card = _card_for_alias(environment, scenario.card_alias)
    flow = ResultMatrixFlow.THREE_DS if scenario.requires_3ds else ResultMatrixFlow.MOTO
    acs_classification = (
        AcsScreenClassification.NOT_REACHED
        if scenario.requires_3ds
        else AcsScreenClassification.NOT_APPLICABLE
    )
    return ResultMatrixEntry(
        card_alias=card.alias,
        brand=card.brand,
        flow=flow,
        requires_3ds=scenario.requires_3ds,
        scenario_id=scenario.scenario_id,
        init=InitObservation(outcome=InitOutcome.NOT_RUN),
        acs=AcsObservation(classification=acs_classification),
        payment_list=PaymentListObservation(outcome=PaymentListOutcome.NOT_QUERIED),
        notes=("template_row",),
    )


def _card_for_alias(environment: PaymentEnvironment, alias: str) -> TestCard:
    for card in environment.cards:
        if card.alias == alias:
            return card
    raise LookupError(f"card alias not configured: {alias}")


if __name__ == "__main__":
    main()
