"""Streak T-1 read offset — gate_profile is the only regression signal.

Pipeline-review on 2026-05-13 misclassified the two-phase write signature
of streak_alert as a CRITICAL split-brain bug. The T-1 offset is
load-bearing (commit da47dc62): same daily_records row carries TODAY's
streak_alert_json next to YESTERDAY's gate_decision_json snapshot. Only
``gate_profile`` divergence between the two is a regression signal.
"""

from __future__ import annotations


def is_streak_regression(today: dict, yesterday_snapshot: dict) -> bool:
    """Return True only when the streak gate profile actually shifted.

    Length / start_date divergence is the expected two-phase write
    signature; the gate decision was already committed yesterday off the
    snapshot, so today's recomputed values do not invalidate that decision.
    """
    return today.get("gate_profile") != yesterday_snapshot.get("gate_profile")


def test_length_divergence_only_is_not_regression() -> None:
    today = {"length": 10, "start_date": "2026-04-28", "gate_profile": "belief_flattening"}
    yesterday = {"length": 4, "start_date": "2026-05-07", "gate_profile": "belief_flattening"}
    assert is_streak_regression(today, yesterday) is False


def test_gate_profile_divergence_is_regression() -> None:
    today = {"length": 10, "gate_profile": "structural_review"}
    yesterday = {"length": 10, "gate_profile": "belief_flattening"}
    assert is_streak_regression(today, yesterday) is True


def test_identical_snapshots_not_regression() -> None:
    snap = {"length": 5, "gate_profile": "relief_unlock"}
    assert is_streak_regression(snap, snap) is False
