"""SWI-115 invariant — ATR_TRAIL setups keep ``target=None`` and
``risk_reward=None`` after the picks exit-strategy dispatcher mutates the
setup in place.

The synthetic helpers added by SWI-307 (and recalibrated in the SWI-316
follow-up) are scoring/simulator-only and must never write back to
``setup``. A regression that flips either field to a numeric value would
re-introduce the SWI-115 critic-quality-bar bug ("BUY with R:R 0.0").
"""

from __future__ import annotations

from unittest.mock import patch

from agents.picks_exit_dispatch import apply_exit_strategy


def _trail_levels(*, entry: int, stop: int) -> dict:
    return {
        "entry_long": entry,
        "stop_long": stop,
        "trail_anchor": entry,
        "trail_peak": entry,
    }


def test_atr_trail_pass_keeps_target_and_rr_none():
    """A passing ATR_TRAIL candidate leaves setup[target]/setup[risk_reward] None."""
    setup: dict = {
        "valid": True,
        "close": 47000,
        "entry": 47000,
        "stop": 46500,
        "target": None,
        "risk_reward": None,
    }
    tech = {"atr": 1000, "close": 47000, "adx": 30}

    # Stub the trail rr_gate to True so dispatch reaches the mutate branch.
    fake_state = {
        "entry_price": 47000,
        "stop_price": 46500,
        "trail_mult": 2.0,
        "atr": 1000,
        "adx": 30.0,
        "regime": "CALM",
        "strategy": "TREND",
        "has_positive_catalyst": False,
        "daily_limit_pct": 0.07,
    }

    class _Stub:
        def build_exit_state(self, *, levels, close, atr, regime):  # noqa: D401, ARG002
            return fake_state

        def rr_gate(self, _state, _floor):  # noqa: D401
            return True

    with patch("agents.picks_exit_dispatch.resolve_exit_strategy", return_value=_Stub()):
        passed, family, rr = apply_exit_strategy(
            ticker="TEST",
            strategy="TREND",
            setup=setup,
            tech_data=tech,
            levels=_trail_levels(entry=47000, stop=46500),
            risk_regime="CALM",
            boosted=set(),
            min_rr=3.0,
            chosen_rr=0.0,
        )

    assert passed is True
    assert family == "ATR_TRAIL"
    assert rr == 0.0
    # SWI-115 load-bearing invariant:
    assert setup["target"] is None
    assert setup["risk_reward"] is None
    assert setup["exit_family"] == "ATR_TRAIL"
