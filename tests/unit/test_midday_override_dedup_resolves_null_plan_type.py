"""SWI-254: LLM-emitted plan_type=null and guardrail SWING must collapse."""

from __future__ import annotations

from agents.midday.guardrails import _append_override, resolve_plan_type_for_ticker
from agents.midday.models import (
    AfternoonAction,
    MiddayQualitative,
    RecommendationOverride,
)


def _empty_qualitative(overrides: list[RecommendationOverride]) -> MiddayQualitative:
    return MiddayQualitative(
        morning_reflection="",
        afternoon_plan=[
            AfternoonAction(ticker="ACV", action="HOLD", confidence="LOW", reason="placeholder")
        ],
        afternoon_note=None,
        capital_note="",
        recommendation_overrides=overrides,
    )


def _resolve_llm_nulls(q: MiddayQualitative, holdings: dict) -> None:
    """Mirror the SWI-254 loop in agents/midday/__init__.py."""
    for o in q.recommendation_overrides:
        if o.plan_type is None:
            o.plan_type = resolve_plan_type_for_ticker(o.ticker, holdings)


def test_llm_null_and_guardrail_swing_collapse_to_one_row():
    """Reproduces ACV 2026-05-05 dedup miss."""
    q = _empty_qualitative(
        [
            RecommendationOverride(
                ticker="ACV",
                plan_type=None,
                morning_action="HOLD",
                midday_status="CANCEL",
                reason="signal cancelled — stop breached intraday",
                revised_stop=44910,
            )
        ]
    )
    holdings = {"ACV": [{"ticker": "ACV", "plan_type": "SWING"}]}

    _resolve_llm_nulls(q, holdings)
    _append_override(
        q,
        ticker="ACV",
        plan_type=None,  # auto-guardrail emits None and resolves through holdings
        morning_action="HOLD",
        reason="Stop breached at 44,910 — auto-generated guardrail",
        holdings_by_ticker=holdings,
    )

    assert len(q.recommendation_overrides) == 1
    assert q.recommendation_overrides[0].plan_type == "SWING"


def test_off_portfolio_override_keeps_null_plan_type():
    q = _empty_qualitative(
        [
            RecommendationOverride(
                ticker="XYZ",
                plan_type=None,
                morning_action="WATCH",
                midday_status="CONFIRM",
                reason="signal still valid",
            )
        ]
    )
    holdings: dict[str, list[dict]] = {}

    _resolve_llm_nulls(q, holdings)
    assert q.recommendation_overrides[0].plan_type is None


def test_dual_listed_ticker_resolves_to_BOTH_then_dedups():
    q = _empty_qualitative(
        [
            RecommendationOverride(
                ticker="FPT",
                plan_type=None,
                morning_action="HOLD",
                midday_status="CANCEL",
                reason="signal cancelled — stop breached",
                revised_stop=80000,
            )
        ]
    )
    holdings = {
        "FPT": [
            {"ticker": "FPT", "plan_type": "SWING"},
            {"ticker": "FPT", "plan_type": "LONGTERM"},
        ]
    }
    _resolve_llm_nulls(q, holdings)
    _append_override(
        q,
        ticker="FPT",
        plan_type=None,
        morning_action="HOLD",
        reason="Stop breached — auto-guardrail",
        holdings_by_ticker=holdings,
    )
    assert len(q.recommendation_overrides) == 1
    assert q.recommendation_overrides[0].plan_type == "BOTH"
