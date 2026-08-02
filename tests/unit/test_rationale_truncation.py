"""Regression: rationale truncation must use split_first_sentence.

Hard `text[:N]` slicing cut through decimals like `84.5k` → `84` and broke
reader trust. All rationale surfaces (my_holdings, what_to_do_today,
rendering/models, midday) route through `split_first_sentence` which only
splits on `.` followed by whitespace.
"""

from __future__ import annotations

import pytest

from shared.text_utils import split_first_sentence


@pytest.mark.parametrize(
    "text, expected_prefix",
    [
        ("Stop at 84.5k. RSI 38 oversold", "Stop at 84.5k"),
        ("Entry 32.5k", "Entry 32.5k"),  # no boundary
        ("R:R 3.2. Wait for pullback", "R:R 3.2"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_split_first_sentence_handles_decimals(text, expected_prefix):
    result = split_first_sentence(text, max_len=180)
    assert result == expected_prefix


def test_what_to_do_today_uses_split_first_sentence():
    """HoldingAction rationale with decimal gets first sentence, not mid-word cut."""
    from pipeline.rendering.models import HoldingAction
    from pipeline.rendering.what_to_do_today import render_what_to_do_today

    action = HoldingAction(
        ticker="FPT",
        verb="TRIM",
        qty_pct=25,
        rationale="Exit partial at 84.5k. Wait for bounce before re-entry.",
        stop_price_vnd=80_000,
        urgency="MEDIUM",
    )
    output = render_what_to_do_today([action], top_picks=None, min_rr_floor=2.0)
    # "84.5k" must be intact — no "84" mid-decimal cut
    assert "84.5k" in output
    assert "Wait for bounce" not in output  # trimmed at sentence boundary


def test_pick_bullet_uses_split_first_sentence():
    """BUY pick note with decimal-containing sentence doesn't truncate mid-number."""
    from pipeline.rendering.what_to_do_today import render_what_to_do_today

    picks = [
        {
            "ticker": "VNM",
            "entry": 80_000,
            "risk_reward": 2.5,
            "why": "Breakout above 78.3k on 2.1x volume. Momentum intact.",
        }
    ]
    output = render_what_to_do_today([], top_picks=picks, min_rr_floor=2.0)
    assert "78.3k" in output
    assert "Momentum intact" not in output  # trimmed at sentence boundary
