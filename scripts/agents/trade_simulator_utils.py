#!/usr/bin/env python3
"""Trade Simulator utilities — helpers and CLI for trade_simulator.py.

Split from trade_simulator.py to stay under 300-line limit.
"""

from .trade_simulator import TradeSimulation, simulate_multiple_trades, simulate_trade


def format_simulation_summary(sim: TradeSimulation) -> str:
    """Format simulation result as human-readable string."""
    lines = [
        f"Simulation for {sim.ticker}:",
        f"  Entry: {sim.entry:,.0f} | Stop: {sim.stop:,.0f} | Target: {sim.target:,.0f}",
        f"  R:R Ratio: {sim.rr_ratio:.1f}",
        f"  Volatility: {sim.volatility_used * 100:.0f}% annualized",
        f"  Results ({sim.num_simulations} sims, {sim.horizon_days} day horizon):",
        f"    P(Target): {sim.p_target:.0%}",
        f"    P(Stop):   {sim.p_stop:.0%}",
        f"    P(Timeout): {sim.p_timeout:.0%}",
        f"    Expected Return: {sim.expected_return_pct:+.1f}%",
        f"    Max Drawdown: {sim.max_drawdown_pct:.1f}%",
        f"    Avg Days to Exit: {sim.avg_days_to_exit:.1f}",
        f"  Recommendation: {sim.recommended_action} [{sim.confidence}]",
        f"  Reason: {sim.reasoning}",
    ]
    return "\n".join(lines)


def format_sim_warning(sim: TradeSimulation) -> str | None:
    """Return warning string for negative EV or high stop probability, else None."""
    if sim.expected_return_pct < 0:
        return f"Monte Carlo: negative EV ({sim.expected_return_pct:+.1f}%)"
    if sim.p_stop > 0.5:
        return f"Monte Carlo: high stop probability ({sim.p_stop:.0%})"
    return None


# ============================================================================
# CLI entry point
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Trade Simulation Test")
    print("=" * 60)

    # Good setup: TCB with proper R:R
    sim1 = simulate_trade(
        ticker="TCB",
        entry=35000,
        stop=33000,
        target=40000,
        volatility=0.35,
        drift=0.05,
    )
    print("\n" + format_simulation_summary(sim1))

    # Bad setup: Low R:R
    sim2 = simulate_trade(
        ticker="VHM",
        entry=110000,
        stop=105000,
        target=115000,
        volatility=0.40,
        drift=-0.05,
    )
    print("\n" + format_simulation_summary(sim2))

    # Invalid setup: Stop >= Entry
    sim3 = simulate_trade(
        ticker="FPT",
        entry=95000,
        stop=96000,  # Invalid!
        target=105000,
        volatility=0.30,
    )
    print("\n" + format_simulation_summary(sim3))

    # Batch test
    trades = [
        {"ticker": "FPT", "entry": 95000, "stop": 90000, "target": 110000},
        {"ticker": "NLG", "entry": 28000, "stop": 26000, "target": 35000},
    ]
    technicals_map = {
        "FPT": {"levels": {"range_20d_high": 112000, "range_20d_low": 88000}, "close": 95000},
    }
    results = simulate_multiple_trades(trades, technicals_map)
    print(f"\nBatch: {len(results)} simulations")
    for r in results:
        w = format_sim_warning(r)
        print(f"  {r.ticker}: EV={r.expected_return_pct:+.1f}% {('⚠ ' + w) if w else '✓'}")
