"""Midday-side narrative-truth validators (SWI-255).

The midday agent authors `RecommendationOverride.reason` text. That text
is later read by retro_commentary which can mistake outcome verbs for
execution facts. Block outcome-verb prose at the agent boundary; the
DB-boundary gate in `shared.neon.insert_midday` is the second line of
defence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shared.narrative import _EXECUTION_PHRASES, narrative_truth_check


@dataclass
class MiddayViolation:
    ticker: str
    check: str
    severity: str
    detail: str
    suggestion: str


@dataclass
class MiddayValidationResult:
    violations: list[MiddayViolation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.violations


def _check_override_reason_signal_language(
    override: dict,
    result: MiddayValidationResult,
) -> None:
    """Reject outcome-verb prose in `reason` — signal language only.

    Midday cannot observe executions, so outcome verbs in reason text
    are always a fabrication risk. expected=None means "the structural
    state is 'no execution observed'", so any execution phrase is wrong.
    """
    violation = narrative_truth_check(
        override.get("reason") or "",
        phrases=_EXECUTION_PHRASES,
        structural_value=False,  # midday never observes executions
        expected=True,
        check_name="OVERRIDE_REASON_OUTCOME_VERB",
        severity="critical",
        detail=(
            "Override reason uses outcome verbs (executed/closed/taken/stopped out) "
            "but midday cannot observe executions."
        ),
        suggestion=(
            "Rewrite using signal language: 'signal cancelled', 'stop level breached "
            "intraday', 'morning thesis invalidated'."
        ),
    )
    if violation:
        result.violations.append(
            MiddayViolation(
                ticker=override.get("ticker") or "?",
                check=violation.check,
                severity=violation.severity,
                detail=violation.detail,
                suggestion=violation.suggestion,
            )
        )


def validate_midday_overrides(overrides: list[dict]) -> MiddayValidationResult:
    """Validate every recommendation_override against narrative-truth rules."""
    result = MiddayValidationResult()
    for override in overrides:
        if not isinstance(override, dict):
            continue
        _check_override_reason_signal_language(override, result)
    return result


__all__ = [
    "MiddayValidationResult",
    "MiddayViolation",
    "_check_override_reason_signal_language",
    "validate_midday_overrides",
]
