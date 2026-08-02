"""SWI-316 follow-up — simulator yields non-degenerate p_target on the
recalibrated 2*ATR synthetic targets (Defect 4).

Pre-fix the 3*ATR target landed beyond the 10-day GBM 1σ reach for typical
VN-stock volatility, so `p_target` came back as a hard 0. We don't assert
a specific value (Monte Carlo is stochastic) — we assert it crosses a
modest floor and that the SKIP-input fast paths still return 0.
"""

from __future__ import annotations

from agents.trade_simulator import simulate_trade
from shared.rules.exit_strategy import derive_atr_trail_synthetic_target


def _sim(entry: int, stop: int, atr: int, volatility: float = 0.40):
    target = derive_atr_trail_synthetic_target(entry=entry, atr=atr)
    return simulate_trade(
        ticker="TEST",
        entry=float(entry),
        stop=float(stop),
        target=float(target),
        volatility=volatility,
        num_sims=200,
        horizon_days=10,
    )


def test_p_target_nondegenerate_sab_like():
    """SAB-like setup (entry=47000, stop=46500, atr=1000) → p_target > 0.05."""
    sim = _sim(entry=47000, stop=46500, atr=1000)
    assert sim.p_target > 0.05, (
        f"p_target={sim.p_target} — recalibrated 2*ATR target is still "
        "outside the 10-day GBM reach for VN-typical vol; consider "
        "lowering SYNTHETIC_TARGET_ATR_MULT to 1.5."
    )


def test_p_target_nondegenerate_wide_atr_tight_stop():
    """Wide-ATR pathological case (entry=47000, stop=46900, atr=2000)."""
    sim = _sim(entry=47000, stop=46900, atr=2000)
    assert sim.p_target > 0.05


def test_p_target_zero_when_stop_above_entry():
    """Invalid setup → fast-path zero, not a recalibration regression."""
    sim = simulate_trade(
        ticker="TEST",
        entry=47000.0,
        stop=47500.0,
        target=49000.0,
        volatility=0.40,
        num_sims=100,
        horizon_days=10,
    )
    assert sim.p_target == 0
