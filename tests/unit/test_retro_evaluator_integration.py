"""Retro evaluator: persisted rule_applied matches classify_retro_rule.

Covers the wire-up added by MON-2026-04-22-007: after compute_evaluations
each row must carry a `rule_applied` field sourced from the Python
classifier, independent of any LLM call.
"""

from __future__ import annotations

from datetime import date

import pytest

from agents.retro import evaluator as evaluator_module
from shared.rules.retro_rule_classifier import classify_retro_rule


class _StubCommentary:
    """Minimal object implementing the EvaluationCommentary protocol subset the
    evaluator touches on the happy path."""

    def __init__(self) -> None:
        self.analyses: list = []
        self.key_insight = "stub"
        self.midday_summary = None
        self.adjustment_effectiveness = "N/A"


@pytest.mark.asyncio
async def test_rule_applied_matches_classifier_for_every_row(
    monkeypatch, mock_trading_config
) -> None:
    recommendations = [
        {
            "ticker": "FPT",
            "action": "BUY",
            "entry_price": 97000,
            "stop_price": 94000,
            "target_price": 103000,
            "section": "ENTRY",
            "plan_type": "SWING",
        },
        {
            "ticker": "HPG",
            "action": "HOLD",
            "entry_price": None,
            "stop_price": None,
            "target_price": None,
            "section": "HOLDING",
            "plan_type": "SWING",
        },
        {
            "ticker": "MWG",
            "action": "WATCH",
            "entry_price": None,
            "stop_price": None,
            "target_price": None,
            "section": "WATCHLIST",
            "plan_type": "SWING",
        },
    ]
    eod_prices = {
        "FPT": {"open": 97.5, "high": 98.2, "low": 96.8, "close": 97.9, "prev_close": 97.0},
        "HPG": {"open": 24.1, "high": 24.5, "low": 23.9, "close": 24.3, "prev_close": 24.0},
        "MWG": {"open": 52.0, "high": 52.8, "low": 51.7, "close": 52.4, "prev_close": 52.1},
    }

    async def _stub_commentary(*_args, **_kwargs):
        return _StubCommentary()

    async def _stub_critic(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(evaluator_module, "get_llm_commentary", _stub_commentary)
    monkeypatch.setattr(evaluator_module, "_run_critic_audit", _stub_critic)

    result = await evaluator_module.evaluate_day_with_agent(
        recommendations=recommendations,
        eod_prices=eod_prices,
        scan_date=date(2026, 4, 22),
        midday_data=None,
        holdings=None,
        closed_trades=None,
    )

    evaluations = result["evaluations"]
    assert evaluations, "evaluator should produce rows for non-empty recs"

    for row in evaluations:
        assert "rule_applied" in row, f"missing rule_applied on {row['ticker']}"
        expected = classify_retro_rule(row)
        assert row["rule_applied"] == expected, (
            f"rule mismatch on {row['ticker']}: persisted={row['rule_applied']} expected={expected}"
        )


# ── Bug 9 (run2 2026-05-14): deterministic key_insight on commentary failure ──
# retro_commentary fully failed (6/6 model-hop timeouts) → get_llm_commentary
# returned None → the else-branch never assigned key_insight → "" shipped to
# daily_record. The fix substitutes a deterministic factual one-liner.

_BUG9_RECS = [
    {
        "ticker": "FPT",
        "action": "BUY",
        "entry_price": 97000,
        "stop_price": 94000,
        "target_price": 103000,
        "section": "ENTRY",
        "plan_type": "SWING",
    }
]
_BUG9_PRICES = {"FPT": {"open": 97.5, "high": 98.2, "low": 96.8, "close": 97.9, "prev_close": 97.0}}


@pytest.mark.asyncio
async def test_key_insight_substituted_when_commentary_fails(
    monkeypatch, mock_trading_config
) -> None:
    """get_llm_commentary returns None → day_summary.key_insight is a
    non-empty deterministic string, never the '' default."""

    async def _no_commentary(*_args, **_kwargs):
        return None

    async def _stub_critic(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(evaluator_module, "get_llm_commentary", _no_commentary)
    monkeypatch.setattr(evaluator_module, "_run_critic_audit", _stub_critic)

    result = await evaluator_module.evaluate_day_with_agent(
        recommendations=_BUG9_RECS,
        eod_prices=_BUG9_PRICES,
        scan_date=date(2026, 5, 14),
        midday_data=None,
        holdings=None,
        closed_trades=None,
    )

    key_insight = result["day_summary"]["key_insight"]
    assert isinstance(key_insight, str)
    assert key_insight, "key_insight must never ship empty when commentary fails"
    assert "commentary unavailable" in key_insight.lower()


@pytest.mark.asyncio
async def test_successful_commentary_key_insight_not_overwritten(
    monkeypatch, mock_trading_config
) -> None:
    """A successful LLM key_insight is preserved — the deterministic
    fallback assigns ONLY in the commentary-is-None branch."""

    async def _stub_commentary(*_args, **_kwargs):
        return _StubCommentary()

    async def _stub_critic(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(evaluator_module, "get_llm_commentary", _stub_commentary)
    monkeypatch.setattr(evaluator_module, "_run_critic_audit", _stub_critic)

    result = await evaluator_module.evaluate_day_with_agent(
        recommendations=_BUG9_RECS,
        eod_prices=_BUG9_PRICES,
        scan_date=date(2026, 5, 14),
        midday_data=None,
        holdings=None,
        closed_trades=None,
    )

    assert result["day_summary"]["key_insight"] == "stub"
