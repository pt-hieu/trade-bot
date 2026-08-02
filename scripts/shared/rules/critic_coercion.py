"""Shared severity coercion for critic agents.

When a critic emits a non-zero severity with no issues, the JSON output is
silently contradictory — downstream consumers see no findings while the
summary reads as a finding. We coerce to "none" and emit
``post_llm_rule.coerced rule_id=critic_severity`` via ``emit_rule_outcome``;
that is the sole emit path.
"""

from __future__ import annotations

from typing import Protocol

from shared.observability_post_llm import emit_rule_outcome

NON_ZERO_SEVERITIES: tuple[str, ...] = ("minor", "major", "critical")


class _CritiqueLike(Protocol):
    # Read-only protocol attrs so concrete Literal-typed fields on Pydantic
    # models satisfy the protocol despite invariant mutable-attribute rules.
    @property
    def severity(self) -> str: ...
    @property
    def issues(self) -> list: ...
    @property
    def summary(self) -> str: ...


def coerce_severity_when_issues_empty(model: _CritiqueLike, *, agent: str) -> None:
    if model.severity in NON_ZERO_SEVERITIES and not model.issues:
        original = model.severity
        summary_text = getattr(model, "summary", "")

        emit_rule_outcome(
            "critic_severity",
            "coerced",
            agent=agent,
            reason="severity_with_empty_issues",
            fields_changed=("severity",),
            boundary="validator",
            metadata={"original_severity": original, "summary": summary_text},
        )

        object.__setattr__(model, "severity", "none")
        # has_issues is a computed_field on critic models — derives from issues
        # automatically. No setattr needed.
