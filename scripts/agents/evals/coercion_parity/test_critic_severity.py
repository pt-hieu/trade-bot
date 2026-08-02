"""Emit-presence tests for critic_coercion (SWI-206)."""

from __future__ import annotations

from dataclasses import dataclass, field

from shared.rules.critic_coercion import coerce_severity_when_issues_empty


@dataclass
class _Critique:
    severity: str
    issues: list = field(default_factory=list)
    summary: str = ""
    has_issues: bool = False


def test_severity_with_empty_issues_emits_and_coerces(
    capture_emits: list[dict],
) -> None:
    critique = _Critique(severity="major", issues=[], summary="found nothing actually")
    coerce_severity_when_issues_empty(critique, agent="critic_test")

    coerced = [e for e in capture_emits if e["outcome"] == "coerced"]
    assert len(coerced) == 1
    e = coerced[0]
    assert e["rule_id"] == "critic_severity"
    assert e["reason"] == "severity_with_empty_issues"
    assert "severity" in e["fields_changed"]
    assert critique.severity == "none"


def test_severity_none_no_emit(capture_emits: list[dict]) -> None:
    critique = _Critique(severity="none", issues=[])
    coerce_severity_when_issues_empty(critique, agent="critic_test")
    assert capture_emits == []
    assert critique.severity == "none"


def test_severity_with_issues_no_emit(capture_emits: list[dict]) -> None:
    critique = _Critique(severity="major", issues=[{"k": "v"}])
    coerce_severity_when_issues_empty(critique, agent="critic_test")
    assert capture_emits == []
    assert critique.severity == "major"
