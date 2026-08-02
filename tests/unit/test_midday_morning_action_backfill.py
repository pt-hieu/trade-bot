"""Bug 2 (run2 2026-05-14): midday fabricated morning_action='TRIM' for ACV.

`morning_action` is a provenance FACT (what the morning rec said), not a
midday judgment. The LLM collapsed ACV's conditional counter-thesis into a
firm 'TRIM'; Python now overwrites every override's `morning_action` from
`morning_action_by_ticker` in the post-LLM loop.

Mirrors the post-LLM loop in agents/midday/__init__.py — the same testing
pattern as test_midday_override_dedup_resolves_null_plan_type.py.
"""

from __future__ import annotations

import pytest

from agents.midday.guardrails import resolve_plan_type_for_ticker
from agents.midday.models import RecommendationOverride


def _apply_post_llm_loop(
    overrides: list[RecommendationOverride],
    holdings_by_ticker: dict,
    morning_action_by_ticker: dict[str, str],
) -> None:
    """Mirror of the post-LLM override loop in agents/midday/__init__.py:
    plan_type resolution + morning_action provenance backfill."""
    for override in overrides:
        if override.plan_type is None:
            override.plan_type = resolve_plan_type_for_ticker(override.ticker, holdings_by_ticker)
        override.morning_action = morning_action_by_ticker.get(override.ticker) or "HOLD"


@pytest.mark.parametrize(
    "morning_action_by_ticker,expected",
    [
        ({"ACV": "EVALUATE"}, "EVALUATE"),  # backfilled from the morning rec
        ({"OTHER": "BUY"}, "HOLD"),  # ticker absent from morning brief → HOLD
    ],
)
def test_morning_action_overwritten_from_morning_recs(morning_action_by_ticker, expected):
    override = RecommendationOverride(
        ticker="ACV",
        plan_type="SWING",
        morning_action="TRIM",  # LLM-fabricated directive
        midday_status="CONFIRM",
        reason="signal still valid",
    )

    _apply_post_llm_loop([override], {}, morning_action_by_ticker)

    assert override.morning_action == expected
