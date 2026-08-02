"""SWI-125 Surface 2: pre-filter R:R floor inside picks.py — single source of truth.

The May 12 incident shipped a 'BUY SAB at 44 (R:R 0.9)' bullet in WHAT TO DO
TODAY because the LLM-side picks writer applied the R:R floor in prose but the
deterministic renderer at what_to_do_today.py:_pick_bullets read raw
pre_computed_picks without filtering. Moving the filter upstream into picks.py
makes every downstream consumer (LLM writer, structured rec builder, renderer,
alert_registrar, strategy_director, entry_strategist) see the same gate-passed
list.
"""

from __future__ import annotations


def test_fixed_target_below_floor_filtered_out() -> None:
    import pipeline  # noqa: F401 — break circular import (pipeline.__init__ loads phase_picks)
    from agents.picks import _passes_rr_floor

    pick = {"ticker": "SAB", "risk_reward": 0.9, "exit_family": "FIXED_TARGET"}
    assert _passes_rr_floor(pick, min_rr=2.0) is False


def test_fixed_target_at_floor_kept() -> None:
    # SWI-137: raw-float comparison, not rounded.
    import pipeline  # noqa: F401 — break circular import (pipeline.__init__ loads phase_picks)
    from agents.picks import _passes_rr_floor

    pick = {"ticker": "FPT", "risk_reward": 2.0, "exit_family": "FIXED_TARGET"}
    assert _passes_rr_floor(pick, min_rr=2.0) is True


def test_fixed_target_above_floor_kept() -> None:
    import pipeline  # noqa: F401 — break circular import (pipeline.__init__ loads phase_picks)
    from agents.picks import _passes_rr_floor

    pick = {"ticker": "TCB", "risk_reward": 3.5, "exit_family": "FIXED_TARGET"}
    assert _passes_rr_floor(pick, min_rr=2.0) is True


def test_atr_trail_with_none_rr_kept() -> None:
    """ATR_TRAIL exits emit risk_reward=None — bypass floor by design."""
    import pipeline  # noqa: F401 — break circular import (pipeline.__init__ loads phase_picks)
    from agents.picks import _passes_rr_floor

    pick = {"ticker": "VNM", "risk_reward": None, "exit_family": "ATR_TRAIL"}
    assert _passes_rr_floor(pick, min_rr=2.0) is True


def test_missing_risk_reward_key_treated_as_none_and_kept() -> None:
    """Defensive: dict without the key behaves identically to None."""
    import pipeline  # noqa: F401 — break circular import (pipeline.__init__ loads phase_picks)
    from agents.picks import _passes_rr_floor

    pick = {"ticker": "VNM", "exit_family": "ATR_TRAIL"}
    assert _passes_rr_floor(pick, min_rr=2.0) is True


def test_raw_float_below_floor_just_under_is_filtered() -> None:
    """SWI-137 raw-float: 1.9999... must fail a 2.0 floor (no rounding)."""
    import pipeline  # noqa: F401 — break circular import (pipeline.__init__ loads phase_picks)
    from agents.picks import _passes_rr_floor

    pick = {"ticker": "X", "risk_reward": 1.9999, "exit_family": "FIXED_TARGET"}
    assert _passes_rr_floor(pick, min_rr=2.0) is False
