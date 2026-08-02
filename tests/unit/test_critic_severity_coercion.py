"""SWI-141 + 2026-05-07 pipeline review: critic schema regression tests.

Two compounding incidents pinned by these tests:

  * 2026-04-29 (SWI-141): retro_eval_critic emitted severity=critical with
    issues=[] and summary describing the defect. Schema permitted the
    contradiction; coercion validator was added.
  * 2026-05-07 (FPT mismatch): critic emitted has_issues=False + severity=none
    + issues=[] + summary describing the defect (verb mismatch). The flat
    schema let four LLM-emitted fields drift independently.

Fix: ``has_issues`` and ``summary`` are now ``@computed_field`` derivations
of ``issues``. The LLM cannot emit them; they cannot diverge by construction.
``severity`` is still LLM-emitted and the original coercion validator (this
file) still pins ``minor/major/critical + issues=[] -> none``.
"""

from __future__ import annotations

from agents.critic import CritiqueIssue, CritiqueResult
from agents.retro.eval_critic import EvalCritiqueResult, IssueItem


def test_eval_critic_severity_coerced_when_issues_empty() -> None:
    """severity=critical + issues=[] -> severity coerced to "none"."""
    result = EvalCritiqueResult(severity="critical", issues=[])
    assert result.severity == "none"
    assert result.has_issues is False


def test_eval_critic_severity_kept_when_issues_present() -> None:
    """severity=critical + issues=[item] -> severity untouched."""
    result = EvalCritiqueResult(
        severity="critical",
        issues=[
            IssueItem(
                ticker="ACV",
                rule_id="vague_lesson",
                confirmed=True,
                note="Lesson reads as boilerplate.",
            )
        ],
    )
    assert result.severity == "critical"
    assert result.has_issues is True


def test_eval_critic_summary_derives_from_first_issue() -> None:
    """summary is computed from issues — not LLM-emitted."""
    result = EvalCritiqueResult(
        severity="major",
        issues=[
            IssueItem(
                ticker="FPT",
                rule_id="vague_lesson",
                confirmed=True,
                note="Boilerplate phrasing.",
            ),
            IssueItem(ticker="ACV", rule_id="metric_misuse", confirmed=True, note="Wrong stop."),
        ],
    )
    assert "vague_lesson" in result.summary
    assert "FPT" in result.summary
    assert "(+1 more)" in result.summary


def test_critic_severity_coerced_when_issues_empty() -> None:
    """severity=major + issues=[] -> severity coerced to "none"; has_issues derived False."""
    result = CritiqueResult(severity="major", issues=[], sections_reviewed=["TOP PICKS"])
    assert result.severity == "none"
    assert result.has_issues is False


def test_critic_has_issues_derived_from_issues_list() -> None:
    """has_issues is a computed_field — populated issues -> True, no LLM emission."""
    result = CritiqueResult(
        severity="major",
        issues=[
            CritiqueIssue(
                category="verb_mismatch",
                location="MY HOLDINGS / FPT",
                description="Header says HOLD; paragraph starts with TRIM.",
                fix="Rewrite paragraph starting with HOLD.",
            )
        ],
        sections_reviewed=["MY HOLDINGS"],
    )
    assert result.has_issues is True
    assert "verb_mismatch" in result.summary
    assert "FPT" in result.summary


def test_critic_summary_no_issues_includes_sections_count() -> None:
    """Empty issues -> summary mentions the section count for operator visibility."""
    result = CritiqueResult(
        severity="none",
        issues=[],
        sections_reviewed=["MY HOLDINGS", "TOP PICKS", "WHAT TO DO TODAY"],
    )
    assert "3 sections" in result.summary


def test_critic_error_severity_preserves_shape() -> None:
    """severity=error is the agent-failure marker — not coerced."""
    result = CritiqueResult(
        severity="error",
        issues=[
            CritiqueIssue(
                category="other",
                location="critic",
                description="Critic execution failed.",
                fix="Investigate critic agent failure logs.",
            )
        ],
    )
    assert result.severity == "error"
    assert result.has_issues is True
