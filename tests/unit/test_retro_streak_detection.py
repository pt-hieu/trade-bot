"""Tests for the deterministic 0-BUY streak detector.

Group 7 of 2026-04-19 pipeline review fixes.
"""

from __future__ import annotations

import pytest

from agents.retro.streak import assert_streak_fetch_nonempty, detect_zero_buy_streak


def _row(date: str, buy_rec_count: int, buy_signal_count: int = 0, regime: str = "NEUTRAL") -> dict:
    return {
        "record_date": date,
        "buy_rec_count": buy_rec_count,
        "buy_signal_count": buy_signal_count,
        "market_regime": regime,
    }


def test_no_streak_when_under_threshold():
    rows = [
        _row("2026-04-15", 2),
        _row("2026-04-16", 1),
        _row("2026-04-17", 0),
        _row("2026-04-18", 0),
        _row("2026-04-19", 1),
    ]
    assert detect_zero_buy_streak(rows) is None


def test_full_window_zero_buy_returns_streak_length_5():
    rows = [_row(f"2026-04-{15 + i:02d}", 0) for i in range(5)]
    streak = detect_zero_buy_streak(rows)
    assert streak is not None
    assert streak.length == 5
    assert streak.start_date == "2026-04-15"


def test_three_of_five_at_tail_triggers():
    rows = [
        _row("2026-04-15", 2),
        _row("2026-04-16", 1),
        _row("2026-04-17", 0),
        _row("2026-04-18", 0),
        _row("2026-04-19", 0),
    ]
    streak = detect_zero_buy_streak(rows)
    assert streak is not None
    assert streak.length == 3


def test_empty_input_returns_none():
    assert detect_zero_buy_streak([]) is None


def test_streak_length_not_truncated_at_10():
    """SWI-346: a 12-day contiguous zero-buy streak reports length >= 12.

    The retro fetch previously bounded the scan to LIMIT 10, silently capping
    the reported streak length below the detector's 30-day length window.
    Feeding 12 contiguous zero-buy rows must surface the full length.
    """
    rows = [_row(f"2026-04-{1 + i:02d}", 0, buy_signal_count=1, regime="NORMAL") for i in range(12)]
    streak = detect_zero_buy_streak(rows)
    assert streak is not None
    assert streak.length >= 12


def test_empty_fetch_fails_loud():
    """SWI-374: a SUCCESSFUL fetch returning 0 rows is a daily_records gap and
    must raise — distinct from detect_zero_buy_streak's None (no-streak) path."""
    with pytest.raises(RuntimeError, match="streak fetch returned 0 rows"):
        assert_streak_fetch_nonempty([], scan_date="2026-05-30", fetch_failed=False)


def test_failed_fetch_does_not_raise_gap():
    """A fetch EXCEPTION stays non-fatal — must not raise the gap error."""
    assert_streak_fetch_nonempty([], scan_date="2026-05-30", fetch_failed=True)  # no raise


def test_nonempty_fetch_does_not_raise():
    assert_streak_fetch_nonempty(
        [{"record_date": "2026-05-30"}], scan_date="2026-05-30", fetch_failed=False
    )


def test_empty_table_bootstrap_does_not_raise():
    """SWI-374: a genuinely empty daily_records table (bootstrap / reseed /
    backfill) is not a per-date gap — it must not abort the whole retro."""
    assert_streak_fetch_nonempty(
        [], scan_date="2026-05-30", fetch_failed=False, table_has_rows=False
    )  # no raise


def test_gate_profile_regime_gated_when_majority_cautious():
    rows = [
        _row("2026-04-17", 0, regime="CAUTIOUS"),
        _row("2026-04-18", 0, regime="CAUTIOUS"),
        _row("2026-04-19", 0, regime="CAUTIOUS"),
    ]
    streak = detect_zero_buy_streak(rows)
    assert streak is not None
    assert streak.gate_profile == "regime_gated"


def test_gate_profile_belief_flattening_when_signals_no_recs():
    rows = [
        _row("2026-04-17", 0, buy_signal_count=5, regime="NEUTRAL"),
        _row("2026-04-18", 0, buy_signal_count=3, regime="NEUTRAL"),
        _row("2026-04-19", 0, buy_signal_count=4, regime="NEUTRAL"),
    ]
    streak = detect_zero_buy_streak(rows)
    assert streak is not None
    assert streak.gate_profile == "belief_flattening"


def test_gate_profile_mixed_when_both_majorities():
    rows = [
        _row("2026-04-17", 0, buy_signal_count=5, regime="CAUTIOUS"),
        _row("2026-04-18", 0, buy_signal_count=3, regime="CAUTIOUS"),
        _row("2026-04-19", 0, buy_signal_count=4, regime="CAUTIOUS"),
    ]
    streak = detect_zero_buy_streak(rows)
    assert streak is not None
    assert streak.gate_profile == "mixed"


# ── SWI-3b.1: trigger window decoupled from length window ──────────


def test_length_reports_true_contiguous_run_beyond_trigger_window():
    """30 trading days of zero-BUY → length=30, not capped at trigger=5."""
    rows = [_row(f"2026-04-{1 + i:02d}", 0) for i in range(30)]
    streak = detect_zero_buy_streak(rows)
    assert streak is not None
    assert streak.length == 30


def test_length_anchors_on_contiguous_suffix_not_full_window():
    """Single BUY 4 days ago → length=4 (contiguous suffix only)."""
    rows = [_row(f"2026-04-{1 + i:02d}", 0) for i in range(30)]
    # Set BUY 4 days from end (index -5)
    rows[-5]["buy_rec_count"] = 1
    streak = detect_zero_buy_streak(rows)
    assert streak is not None
    assert streak.length == 4


def test_length_lookback_at_least_structural_review_threshold():
    """Inter-module contract: detector window >= relief gate's structural tier."""
    from agents.retro.streak import _LENGTH_LOOKBACK_DAYS
    from shared.rules.recommendation_gate import _STREAK_STRUCTURAL_LENGTH

    assert _LENGTH_LOOKBACK_DAYS >= _STREAK_STRUCTURAL_LENGTH, (
        "Length-measurement window must reach the structural-review tier, "
        "otherwise length capping silently disables the relief escalation."
    )


def test_to_jsonb_shape_stable():
    rows = [_row(f"2026-04-{15 + i:02d}", 0) for i in range(3)]
    streak = detect_zero_buy_streak(rows)
    assert streak is not None
    blob = streak.to_jsonb()
    assert set(blob.keys()) == {"length", "start_date", "gate_profile"}
    assert blob["length"] == 3
    assert blob["start_date"] == "2026-04-15"
