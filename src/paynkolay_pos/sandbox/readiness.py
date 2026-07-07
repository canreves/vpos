"""Readiness checks for private Paynkolay sandbox execution."""

from __future__ import annotations

from dataclasses import dataclass

from paynkolay_pos.config import RuntimeSettings
from paynkolay_pos.models import PaymentChannel
from paynkolay_pos.scenarios import PaymentScenarioCatalog


@dataclass(frozen=True)
class SandboxReadinessIssue:
    """One actionable problem that blocks or weakens sandbox execution."""

    code: str
    message: str


@dataclass(frozen=True)
class SandboxReadinessReport:
    """Aggregated readiness result for a private config and scenario catalogue."""

    environment: str
    card_count: int
    scenario_count: int
    issues: tuple[SandboxReadinessIssue, ...]

    @property
    def ready(self) -> bool:
        """Return whether the private sandbox inputs pass all readiness checks."""

        return not self.issues


def check_sandbox_readiness(
    settings: RuntimeSettings,
    catalog: PaymentScenarioCatalog,
    *,
    minimum_card_count: int = 100,
) -> SandboxReadinessReport:
    """Check private runtime inputs before any real provider call is attempted."""

    environment = settings.current
    issues: list[SandboxReadinessIssue] = []
    configured_aliases = {card.alias for card in environment.cards}
    scenario_aliases = {scenario.card_alias for scenario in catalog.scenarios}

    for field_name, value in {
        "merchant_id": environment.merchant.merchant_id,
        "terminal_id": environment.merchant.terminal_id,
        "api_key": environment.merchant.api_key.get_secret_value(),
        "secret_key": environment.merchant.secret_key.get_secret_value(),
        "base_url": environment.base_url,
        "callback_base_url": environment.callback_base_url,
    }.items():
        if _looks_placeholder(value):
            issues.append(
                SandboxReadinessIssue(
                    code="placeholder_value",
                    message=f"{field_name} still contains a placeholder value",
                )
            )

    if len(environment.cards) < minimum_card_count:
        issues.append(
            SandboxReadinessIssue(
                code="insufficient_cards",
                message=(
                    f"configured card count is {len(environment.cards)}; "
                    f"expected at least {minimum_card_count}"
                ),
            )
        )

    missing_aliases = sorted(scenario_aliases - configured_aliases)
    if missing_aliases:
        issues.append(
            SandboxReadinessIssue(
                code="missing_card_aliases",
                message="scenario card aliases missing from config: " + ", ".join(missing_aliases),
            )
        )

    unused_aliases = sorted(configured_aliases - scenario_aliases)
    if unused_aliases:
        issues.append(
            SandboxReadinessIssue(
                code="unused_card_aliases",
                message=f"{len(unused_aliases)} configured card aliases are not used by scenarios",
            )
        )

    for card in environment.cards:
        if card.requires_3ds and card.expected_otp is None:
            issues.append(
                SandboxReadinessIssue(
                    code="missing_otp",
                    message=f"3DS card {card.alias!r} does not define expected_otp",
                )
            )

    for scenario in catalog.scenarios:
        if scenario.moto and scenario.requires_3ds:
            issues.append(
                SandboxReadinessIssue(
                    code="invalid_moto_3ds",
                    message=f"MoTo scenario {scenario.scenario_id!r} must not require 3DS",
                )
            )
        if scenario.payment_channel is PaymentChannel.MOTO and not scenario.moto:
            issues.append(
                SandboxReadinessIssue(
                    code="invalid_moto_channel",
                    message=(
                        f"scenario {scenario.scenario_id!r} uses moto channel "
                        "without moto=true"
                    ),
                )
            )
        if "sandbox" not in scenario.tags:
            issues.append(
                SandboxReadinessIssue(
                    code="missing_sandbox_tag",
                    message=f"scenario {scenario.scenario_id!r} should include the sandbox tag",
                )
            )

    return SandboxReadinessReport(
        environment=environment.name.value,
        card_count=len(environment.cards),
        scenario_count=len(catalog.scenarios),
        issues=tuple(issues),
    )


def format_readiness_report(report: SandboxReadinessReport) -> str:
    """Format a readiness report for CLI output."""

    status = "READY" if report.ready else "NOT READY"
    lines = [
        f"Sandbox readiness: {status}",
        f"Environment: {report.environment}",
        f"Cards: {report.card_count}",
        f"Scenarios: {report.scenario_count}",
    ]
    if report.issues:
        lines.append("Issues:")
        lines.extend(f"- {issue.code}: {issue.message}" for issue in report.issues)
    return "\n".join(lines)


def _looks_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        not normalized
        or "replace-with" in normalized
        or normalized.endswith(".example.test")
        or normalized in {"changeme", "todo", "placeholder"}
    )
