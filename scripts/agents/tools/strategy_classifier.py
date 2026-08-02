#!/usr/bin/env python3
"""Deterministic strategy classification for BUY recommendations.

Classifies each BUY signal into one of 7 trading strategies:
- DIVERGENCE: close <= swing_low + RSI divergence (bullish)
- BREAKOUT: close > resistance + volume >= 1.5x
- BOUNCE: RSI < 40 + price within 5% of support (oversold near support)
- TREND: UPTREND + price near MA20/MA50 + RSI 35-65
- MEAN_REVERSION: RSI < 45 + within 8% of support + DOWNTREND/SIDEWAYS
- MOMENTUM: RSI > 55 + price above MA20 + volume > 1.0x
- PULLBACK: price between MA20 and MA50 in UPTREND/SIDEWAYS

Priority: DIVERGENCE > BREAKOUT > BOUNCE > TREND > MEAN_REVERSION > MOMENTUM > PULLBACK
"""

from dataclasses import dataclass, field

from shared.lint_markers import allow_single_ticker_fetcher


@dataclass
class StrategyClassification:
    strategy: str  # DIVERGENCE | BREAKOUT | BOUNCE | TREND | MEAN_REVERSION | MOMENTUM | PULLBACK | UNCLASSIFIED
    confidence: float  # 0.0-1.0
    matched_signals: list[str] = field(default_factory=list)


def classify_strategy(
    technicals: dict,
    rsi_at_swing_low: float | None = None,
    has_positive_active_catalyst: bool = False,
) -> StrategyClassification:
    """Classify a BUY signal into a trading strategy.

    Priority: DIVERGENCE > BREAKOUT > BOUNCE > TREND > MEAN_REVERSION > MOMENTUM > PULLBACK

    Catalyst promotion: MEAN_REVERSION → MOMENTUM when the ticker has a
    boost-eligible POSITIVE catalyst, so downstream dispatches to ATRTrailExit
    instead of truncating the trade at nearest resistance.

    Args:
        technicals: Full technicals dict from get_ticker_data_async()
        rsi_at_swing_low: RSI value at swing_low_date (for DIVERGENCE check).
                          Pass None to skip DIVERGENCE check.
        has_positive_active_catalyst: True when caller has already resolved
            catalyst lifecycle for this ticker via
            ``catalyst_override.get_catalyst_boosted_tickers``. Drives the
            MR → MOMENTUM promotion.

    Returns:
        StrategyClassification with strategy, confidence, matched_signals
    """
    close = technicals.get("close", 0)
    rsi = technicals.get("rsi")
    ma20 = technicals.get("ma20")
    ma50 = technicals.get("ma50")
    volume_vs_avg = technicals.get("volume_vs_avg")
    trend = technicals.get("trend") or {}
    levels = technicals.get("levels") or {}

    trend_direction = trend.get("trend", "SIDEWAYS")
    swing_low = levels.get("swing_low")
    nearest_support = levels.get("nearest_support")
    nearest_resistance = levels.get("nearest_resistance")
    support_ref = nearest_support or swing_low

    # ── DIVERGENCE ────────────────────────────────────────────────────────────
    # close <= swing_low AND current RSI > RSI at swing_low_date
    if (
        close
        and swing_low
        and rsi is not None
        and rsi_at_swing_low is not None
        and close <= swing_low
        and rsi > rsi_at_swing_low
    ):
        signals = [
            f"price={close:.0f} <= swing_low={swing_low:.0f}",
            f"RSI={rsi:.1f} > RSI_at_low={rsi_at_swing_low:.1f}",
        ]
        confidence = _divergence_confidence(rsi, rsi_at_swing_low)
        return StrategyClassification("DIVERGENCE", confidence, signals)

    # ── BREAKOUT ──────────────────────────────────────────────────────────────
    # close > nearest_resistance AND volume >= 1.5x
    if (
        close
        and nearest_resistance
        and volume_vs_avg is not None
        and close > nearest_resistance
        and volume_vs_avg >= 1.5
    ):
        signals = [
            f"close={close:.0f} > resistance={nearest_resistance:.0f}",
            f"volume={volume_vs_avg:.1f}x avg",
        ]
        confidence = min(1.0, 0.55 + (volume_vs_avg - 1.5) * 0.15)
        return StrategyClassification("BREAKOUT", confidence, signals)

    # ── BOUNCE ────────────────────────────────────────────────────────────────
    # RSI < 40 AND price within 5% of support
    if rsi is not None and rsi < 40 and close and support_ref and support_ref > 0:
        dist_pct = abs(close - support_ref) / support_ref * 100
        if dist_pct <= 5.0:
            signals = [
                f"RSI={rsi:.1f} (oversold)",
                f"price within {dist_pct:.1f}% of support={support_ref:.0f}",
            ]
            confidence = _bounce_confidence(rsi, dist_pct)
            return StrategyClassification("BOUNCE", confidence, signals)

    # ── TREND ─────────────────────────────────────────────────────────────────
    # UPTREND + price within 5% of MA20 or MA50 + RSI 35-65
    if trend_direction == "UPTREND" and rsi is not None and 35 <= rsi <= 65:
        near_ma, signals = _check_near_moving_average(close, ma20, ma50, max_dist_pct=5.0)
        if near_ma:
            signals.append(f"UPTREND RSI={rsi:.1f}")
            return StrategyClassification("TREND", 0.7, signals)

    # ── MEAN_REVERSION ────────────────────────────────────────────────────────
    # RSI < 45 + within 8% of support + DOWNTREND or SIDEWAYS (buy the dip)
    if (
        rsi is not None
        and rsi < 45
        and close
        and support_ref
        and support_ref > 0
        and trend_direction in ("DOWNTREND", "SIDEWAYS")
    ):
        dist_pct = abs(close - support_ref) / support_ref * 100
        if dist_pct <= 8.0:
            signals = [
                f"RSI={rsi:.1f} (weakening)",
                f"{trend_direction} within {dist_pct:.1f}% of support={support_ref:.0f}",
            ]
            # Closer to support + lower RSI = higher confidence
            confidence = min(
                0.85, 0.45 + max(0, (45 - rsi) / 45) * 0.2 + max(0, (8 - dist_pct) / 8) * 0.2
            )
            if has_positive_active_catalyst:
                # Promote to MOMENTUM so ExitStrategy dispatch selects ATRTrailExit.
                # Keep the MR confidence but tag the catalyst-driven signal for audit.
                signals = [*signals, "positive catalyst active → promote MR→MOMENTUM"]
                return StrategyClassification("MOMENTUM", confidence, signals)
            return StrategyClassification("MEAN_REVERSION", confidence, signals)

    # ── MOMENTUM ──────────────────────────────────────────────────────────────
    # RSI > 55 + price above MA20 + volume > 1.0x (riding strength)
    if (
        rsi is not None
        and rsi > 55
        and close
        and ma20
        and close > ma20
        and volume_vs_avg is not None
        and volume_vs_avg > 1.0
    ):
        signals = [
            f"RSI={rsi:.1f} (strong)",
            f"price={close:.0f} > MA20={ma20:.0f}",
            f"volume={volume_vs_avg:.1f}x avg",
        ]
        confidence = min(0.85, 0.5 + (rsi - 55) / 100 + min(0.15, (volume_vs_avg - 1.0) * 0.1))
        return StrategyClassification("MOMENTUM", confidence, signals)

    # ── PULLBACK ──────────────────────────────────────────────────────────────
    # Price between MA20 and MA50 (or near MA50) in UPTREND/SIDEWAYS
    if (
        close
        and ma20
        and ma50
        and ma20 > 0
        and ma50 > 0
        and trend_direction in ("UPTREND", "SIDEWAYS")
    ):
        between_mas = min(ma20, ma50) <= close <= max(ma20, ma50)
        near_ma50 = abs(close - ma50) / ma50 * 100 <= 3.0 if ma50 > 0 else False
        if between_mas or near_ma50:
            signals = [f"price={close:.0f} between MA20={ma20:.0f} and MA50={ma50:.0f}"]
            if near_ma50:
                signals.append("near MA50")
            signals.append(f"{trend_direction}")
            return StrategyClassification("PULLBACK", 0.55, signals)

    return StrategyClassification("UNCLASSIFIED", 0.0, [])


def _check_near_moving_average(
    close: float, ma20: float | None, ma50: float | None, max_dist_pct: float = 5.0
) -> tuple[bool, list[str]]:
    """Check if close is within max_dist_pct of MA20 or MA50."""
    signals = []
    if ma20 and close and ma20 > 0:
        dist_ma20 = abs(close - ma20) / ma20 * 100
        if dist_ma20 <= max_dist_pct:
            signals.append(f"within {dist_ma20:.1f}% of MA20={ma20:.0f}")
            return True, signals
    if ma50 and close and ma50 > 0:
        dist_ma50 = abs(close - ma50) / ma50 * 100
        if dist_ma50 <= max_dist_pct:
            signals.append(f"within {dist_ma50:.1f}% of MA50={ma50:.0f}")
            return True, signals
    return False, signals


def _divergence_confidence(rsi_now: float, rsi_at_low: float) -> float:
    """Higher RSI divergence = higher confidence."""
    rsi_diff = rsi_now - rsi_at_low
    if rsi_diff > 10:
        return 0.9
    if rsi_diff > 5:
        return 0.75
    return 0.6


def _bounce_confidence(rsi: float, dist_pct: float) -> float:
    """Lower RSI and closer to support = higher confidence."""
    rsi_bonus = max(0.0, (40 - rsi) / 40 * 0.3)
    dist_bonus = max(0.0, (5.0 - dist_pct) / 5.0 * 0.2)
    return min(1.0, 0.55 + rsi_bonus + dist_bonus)


@allow_single_ticker_fetcher  # per-ticker swing_low_date differs; batching would require passing (ticker, date) pairs
async def get_rsi_at_swing_low_date(ticker: str, swing_low_date: str | None) -> float | None:
    """Fetch RSI at swing_low_date from price history API for DIVERGENCE check."""
    if not swing_low_date:
        return None

    try:
        date_str = str(swing_low_date)[:10]
        from shared.vnstock_client import fetch_technicals_history

        result = await fetch_technicals_history(
            symbol=ticker.upper(),
            start=date_str,
            end=date_str,
        )
        for record in result.get("data", []):
            rsi_val = record.get("rsi")
            if rsi_val is not None:
                return float(rsi_val)
    except Exception:
        pass
    return None
