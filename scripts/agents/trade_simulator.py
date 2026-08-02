#!/usr/bin/env python3
"""
Trade Simulator using Monte Carlo simulation.

Simulates proposed trades to estimate probability of success and expected value.
Part of the Mental Loop pattern: Propose → Simulate → Refine → Execute
"""

import math
import random
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field


class TradeSimulation(BaseModel):
    """Result from simulating a trade."""

    ticker: str
    entry: float
    stop: float
    target: float
    rr_ratio: float = Field(description="Risk/Reward ratio")

    # Simulation parameters
    num_simulations: int
    horizon_days: int
    volatility_used: float

    # Simulation results
    p_target: float = Field(description="Probability of hitting target")
    p_stop: float = Field(description="Probability of hitting stop")
    p_timeout: float = Field(description="Probability of neither in horizon")

    expected_return_pct: float = Field(description="Weighted average return %")
    max_drawdown_pct: float = Field(description="Worst drawdown observed %")
    avg_days_to_exit: float = Field(description="Average days to hit target or stop")

    # Recommendations
    recommended_action: Literal["TRADE", "SKIP", "REDUCE_SIZE"]
    confidence: Literal["high", "medium", "low"]
    reasoning: str


def calculate_volatility(technicals: dict) -> float:
    """
    Calculate daily volatility from technicals data.

    Uses range-based volatility estimation:
    volatility ≈ (high - low) / close * sqrt(252)

    Args:
        technicals: Dict with price data and levels

    Returns:
        Annualized volatility (decimal, e.g., 0.35 = 35%)
    """
    # Try to get volatility from various sources
    levels = technicals.get("levels", {})

    # Method 1: Use 20-day range
    range_high = levels.get("range_20d_high")
    range_low = levels.get("range_20d_low")
    close = technicals.get("close") or technicals.get("price")

    if range_high and range_low and close and close > 0:
        # Range-based volatility (Parkinson estimator simplified)
        daily_range_pct = (range_high - range_low) / close
        # Approximate: 20-day range / 4 ≈ daily volatility
        daily_vol = daily_range_pct / 4
        return daily_vol * math.sqrt(252)  # Annualize

    # Method 2: Use swing high/low
    swing_high = levels.get("swing_high")
    swing_low = levels.get("swing_low")

    if swing_high and swing_low and close and close > 0:
        range_pct = (swing_high - swing_low) / close
        daily_vol = range_pct / 5  # Assume 5-day swing
        return daily_vol * math.sqrt(252)

    # Default: Use typical Vietnam stock volatility
    return 0.40  # 40% annualized is typical for VN stocks


def get_trend_drift(technicals: dict) -> float:
    """
    Estimate drift (expected daily return) from trend data.

    Args:
        technicals: Dict with trend data

    Returns:
        Annualized drift (decimal)
    """
    trend = technicals.get("trend", {})
    trend_dir = trend.get("trend", "SIDEWAYS")
    momentum = trend.get("momentum", "neutral")

    # Base drift on trend direction
    if trend_dir == "UPTREND":
        base_drift = 0.10  # 10% annualized
    elif trend_dir == "DOWNTREND":
        base_drift = -0.10
    else:
        base_drift = 0.0

    # Adjust for momentum
    if momentum == "bullish":
        base_drift += 0.05
    elif momentum == "bearish":
        base_drift -= 0.05

    return base_drift


def simulate_trade(
    ticker: str,
    entry: float,
    stop: float,
    target: float,
    volatility: float | None = None,
    drift: float = 0.0,
    num_sims: int = 500,
    horizon_days: int = 10,
    technicals: dict | None = None,
) -> TradeSimulation:
    """
    Monte Carlo simulation of a trade.

    Uses Geometric Brownian Motion:
    S(t+1) = S(t) * exp((drift - 0.5*vol^2)*dt + vol*sqrt(dt)*Z)

    Args:
        ticker: Stock ticker
        entry: Entry price
        stop: Stop-loss price
        target: Target price
        volatility: Annualized volatility (if None, calculated from technicals)
        drift: Annualized drift/trend
        num_sims: Number of simulations to run
        horizon_days: Maximum days to simulate
        technicals: Technicals data for volatility calculation

    Returns:
        TradeSimulation with probabilities and recommendation
    """
    # Calculate volatility if not provided
    if volatility is None:
        if technicals:
            volatility = calculate_volatility(technicals)
            drift = get_trend_drift(technicals)
        else:
            volatility = 0.40  # Default 40% annualized

    # Convert to daily
    daily_vol = volatility / math.sqrt(252)
    daily_drift = drift / 252

    # Calculate R:R ratio
    risk = entry - stop
    reward = target - entry
    rr_ratio = reward / risk if risk > 0 else 0

    # Validate inputs
    if stop >= entry:
        return TradeSimulation(
            ticker=ticker,
            entry=entry,
            stop=stop,
            target=target,
            rr_ratio=rr_ratio,
            num_simulations=0,
            horizon_days=horizon_days,
            volatility_used=volatility,
            p_target=0,
            p_stop=1,
            p_timeout=0,
            expected_return_pct=-100 * risk / entry,
            max_drawdown_pct=100 * risk / entry,
            avg_days_to_exit=1,
            recommended_action="SKIP",
            confidence="high",
            reasoning=f"Invalid setup: stop ({stop}) >= entry ({entry})",
        )

    if target <= entry:
        return TradeSimulation(
            ticker=ticker,
            entry=entry,
            stop=stop,
            target=target,
            rr_ratio=rr_ratio,
            num_simulations=0,
            horizon_days=horizon_days,
            volatility_used=volatility,
            p_target=0,
            p_stop=0,
            p_timeout=1,
            expected_return_pct=0,
            max_drawdown_pct=0,
            avg_days_to_exit=horizon_days,
            recommended_action="SKIP",
            confidence="high",
            reasoning=f"Invalid setup: target ({target}) <= entry ({entry})",
        )

    # Run simulations
    hit_target = 0
    hit_stop = 0
    timeout = 0
    returns = []
    drawdowns = []
    days_to_exit = []

    random.seed(42)  # Reproducibility
    np.random.seed(42)

    for _ in range(num_sims):
        price = entry
        min_price = entry
        exit_day = horizon_days

        for day in range(1, horizon_days + 1):
            # GBM step
            z = np.random.normal()
            daily_return = math.exp((daily_drift - 0.5 * daily_vol**2) + daily_vol * z)
            price *= daily_return

            min_price = min(min_price, price)

            # Check exits (check stop first - more conservative)
            if price <= stop:
                hit_stop += 1
                returns.append((stop - entry) / entry * 100)
                exit_day = day
                break
            elif price >= target:
                hit_target += 1
                returns.append((target - entry) / entry * 100)
                exit_day = day
                break
        else:
            # Timeout - neither hit
            timeout += 1
            returns.append((price - entry) / entry * 100)

        drawdown = (entry - min_price) / entry * 100
        drawdowns.append(drawdown)
        days_to_exit.append(exit_day)

    # Calculate statistics
    p_target = hit_target / num_sims
    p_stop = hit_stop / num_sims
    p_timeout = timeout / num_sims
    expected_return = np.mean(returns)
    max_dd = max(drawdowns)
    avg_exit_days = np.mean(days_to_exit)

    # Determine recommendation
    if expected_return < 0:
        action = "SKIP"
        reasoning = f"Negative EV ({expected_return:.1f}%)"
        confidence = "high"
    elif p_stop > 0.5:
        action = "REDUCE_SIZE"
        reasoning = f"High stop probability ({p_stop:.0%}), reduce position"
        confidence = "medium"
    elif p_target > 0.45 and expected_return > 2:
        action = "TRADE"
        reasoning = f"Good odds: {p_target:.0%} to target, EV +{expected_return:.1f}%"
        confidence = "high" if p_target > 0.5 else "medium"
    elif expected_return > 1 and rr_ratio >= 3:
        action = "TRADE"
        reasoning = f"Acceptable EV +{expected_return:.1f}% with R:R {rr_ratio:.1f}"
        confidence = "medium"
    else:
        action = "SKIP"
        reasoning = f"Marginal setup: EV +{expected_return:.1f}%, P(target) {p_target:.0%}"
        confidence = "medium"

    return TradeSimulation(
        ticker=ticker,
        entry=entry,
        stop=stop,
        target=target,
        rr_ratio=rr_ratio,
        num_simulations=num_sims,
        horizon_days=horizon_days,
        volatility_used=volatility,
        p_target=p_target,
        p_stop=p_stop,
        p_timeout=p_timeout,
        expected_return_pct=float(expected_return),
        max_drawdown_pct=float(max_dd),
        avg_days_to_exit=float(avg_exit_days),
        recommended_action=action,
        confidence=confidence,
        reasoning=reasoning,
    )


def simulate_multiple_trades(
    trades: list[dict],
    technicals_map: dict[str, dict],
    num_sims: int = 500,
    horizon_days: int = 10,
) -> list[TradeSimulation]:
    """
    Simulate multiple trades and return results.

    Args:
        trades: List of trade dicts with ticker, entry, stop, target
        technicals_map: Dict mapping ticker to technicals data
        num_sims: Simulations per trade
        horizon_days: Max holding period

    Returns:
        List of TradeSimulation results
    """
    results = []

    for trade in trades:
        ticker = trade.get("ticker")
        entry = trade.get("entry")
        stop = trade.get("stop")
        target = trade.get("target")

        if not ticker or entry is None or stop is None or target is None:
            continue

        technicals = technicals_map.get(ticker, {})

        sim = simulate_trade(
            ticker=ticker,
            entry=entry,
            stop=stop,
            target=target,
            technicals=technicals,
            num_sims=num_sims,
            horizon_days=horizon_days,
        )
        results.append(sim)

    return results


# format_simulation_summary and CLI moved to trade_simulator_utils.py
