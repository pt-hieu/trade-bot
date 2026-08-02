"""
Multi-day price action analysis for spike/gap/pullback detection.

All metrics are computed deterministically in Python (never by LLM).
Exposed to agents via get_ticker_data_async() → result["price_action"].
"""

from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

RALLY_MIN_GAIN_PCT = 15.0  # Min % gain to flag as rally
RALLY_MAX_SESSIONS = 10  # Max sessions for the rally window
RALLY_LOOKBACK_DAYS = 25  # How far back to scan for rally start
GAP_MIN_PCT = 2.0  # Min gap size to flag
VOLUME_STRONG_THRESHOLD = 0.80  # Pullback vol / rally vol ratio
VOLUME_MODERATE_THRESHOLD = 0.50
POST_SPIKE_ABOVE_BASE_PCT = 10.0  # Must be >10% above base for POST_SPIKE


# ---------------------------------------------------------------------------
# Pure Computation Functions
# ---------------------------------------------------------------------------


def analyze_price_action(candles: list[dict], current_close: float) -> dict:
    """Analyze multi-day price action from OHLCV candles.

    Args:
        candles: List of {open, high, low, close, volume, time} dicts,
                 chronological (oldest first). Prices in thousands VND.
        current_close: Current close price in raw VND (e.g., 65000).

    Returns:
        Dict with rally, pullback, volume_profile, gaps, classification,
        risk_flags keys. Returns classification=NORMAL if no spike detected.
    """
    # Convert VND to thousands for display
    close_k = current_close / 1000

    rally = _detect_rally(candles)
    gaps = _detect_gaps(candles)

    if not rally:
        return {
            "rally": None,
            "pullback": None,
            "volume_profile": None,
            "gaps": gaps,
            "classification": "NORMAL",
            "risk_flags": [],
        }

    pullback = _compute_pullback(rally, close_k)
    volume_profile = _analyze_volume_profile(candles, rally)
    classification = _classify(rally, pullback, volume_profile)
    risk_flags = _build_risk_flags(rally, pullback, volume_profile, gaps)

    return {
        "rally": rally,
        "pullback": pullback,
        "volume_profile": volume_profile,
        "gaps": gaps,
        "classification": classification,
        "risk_flags": risk_flags,
    }


def _detect_rally(candles: list[dict]) -> dict | None:
    """Detect a significant rally (>= RALLY_MIN_GAIN_PCT) within the lookback.

    Scans all windows of up to RALLY_MAX_SESSIONS within the last
    RALLY_LOOKBACK_DAYS candles. Returns the largest rally found.
    """
    n = len(candles)
    lookback_start = max(0, n - RALLY_LOOKBACK_DAYS)
    best = None

    for peak_idx in range(lookback_start + 1, n):
        peak_high = candles[peak_idx]["high"]
        # Look back up to RALLY_MAX_SESSIONS for the trough
        window_start = max(lookback_start, peak_idx - RALLY_MAX_SESSIONS)
        for base_idx in range(window_start, peak_idx):
            base_low = candles[base_idx]["low"]
            if base_low <= 0:
                continue
            gain_pct = ((peak_high - base_low) / base_low) * 100
            if gain_pct >= RALLY_MIN_GAIN_PCT and (best is None or gain_pct > best["gain_pct"]):
                best = {
                    "detected": True,
                    "gain_pct": round(gain_pct, 1),
                    "gain_sessions": peak_idx - base_idx,
                    "peak_price": peak_high,
                    "peak_date": _get_date(candles[peak_idx]),
                    "peak_idx": peak_idx,
                    "base_price": base_low,
                    "base_date": _get_date(candles[base_idx]),
                    "base_idx": base_idx,
                }

    if best:
        # Compute pre-rally consolidation zone (5 days before base)
        base_zone = _find_base_zone(candles, best["base_idx"])
        best["pre_rally_zone"] = base_zone

    return best


def _find_base_zone(candles: list[dict], base_idx: int) -> float:
    """Find pre-rally consolidation price (avg of low+close for 5 days before rally)."""
    start = max(0, base_idx - 5)
    zone_candles = candles[start:base_idx]
    if not zone_candles:
        return candles[base_idx]["low"]
    avg = sum((c["low"] + c["close"]) / 2 for c in zone_candles) / len(zone_candles)
    return round(avg, 2)


def _compute_pullback(rally: dict, current_close_k: float) -> dict:
    """Compute pullback metrics from rally peak."""
    peak = rally["peak_price"]
    base = rally["pre_rally_zone"]

    from_peak_pct = ((current_close_k - peak) / peak) * 100 if peak else 0
    above_base_pct = ((current_close_k - base) / base) * 100 if base else 0

    rally_range = peak - base
    retracement_pct = ((peak - current_close_k) / rally_range) * 100 if rally_range > 0 else 0

    # Fibonacci fill zone: 50% to 61.8% retracement
    fib_50 = round(peak - rally_range * 0.50, 1)
    fib_618 = round(peak - rally_range * 0.618, 1)

    return {
        "from_peak_pct": round(from_peak_pct, 1),
        "above_base_pct": round(above_base_pct, 1),
        "retracement_pct": round(retracement_pct, 1),
        "gap_fill_risk": above_base_pct > 5.0,
        "fib_fill_zone": (min(fib_618, fib_50), max(fib_618, fib_50)),
    }


def _detect_gaps(candles: list[dict]) -> list[dict]:
    """Detect unfilled price gaps >= GAP_MIN_PCT."""
    gaps = []
    for i in range(1, len(candles)):
        prev_high = candles[i - 1]["high"]
        prev_low = candles[i - 1]["low"]
        curr_high = candles[i]["high"]
        curr_low = candles[i]["low"]

        # Gap up: today's low > yesterday's high
        if curr_low > prev_high and prev_high > 0:
            gap_pct = ((curr_low - prev_high) / prev_high) * 100
            if gap_pct >= GAP_MIN_PCT:
                gaps.append(
                    {
                        "date": _get_date(candles[i]),
                        "type": "gap_up",
                        "gap_low": prev_high,
                        "gap_high": curr_low,
                        "gap_pct": round(gap_pct, 1),
                        "idx": i,
                    }
                )

        # Gap down: today's high < yesterday's low
        if curr_high < prev_low and prev_low > 0:
            gap_pct = ((prev_low - curr_high) / prev_low) * 100
            if gap_pct >= GAP_MIN_PCT:
                gaps.append(
                    {
                        "date": _get_date(candles[i]),
                        "type": "gap_down",
                        "gap_low": curr_high,
                        "gap_high": prev_low,
                        "gap_pct": round(gap_pct, 1),
                        "idx": i,
                    }
                )

    # Mark filled gaps
    for gap in gaps:
        gap["filled"] = _is_gap_filled(candles, gap)

    # Return only unfilled
    return [g for g in gaps if not g.pop("filled")]


def _is_gap_filled(candles: list[dict], gap: dict) -> bool:
    """Check if gap was filled by subsequent price action."""
    for c in candles[gap["idx"] + 1 :]:
        if gap["type"] == "gap_up" and c["low"] <= gap["gap_low"]:
            return True
        if gap["type"] == "gap_down" and c["high"] >= gap["gap_high"]:
            return True
    return False


def _analyze_volume_profile(candles: list[dict], rally: dict) -> dict:
    """Compare volume during rally vs pullback period."""
    base_idx = rally["base_idx"]
    peak_idx = rally["peak_idx"]

    rally_candles = candles[base_idx : peak_idx + 1]
    pullback_candles = candles[peak_idx + 1 :]

    rally_vols = [c["volume"] for c in rally_candles if c.get("volume")]
    pullback_vols = [c["volume"] for c in pullback_candles if c.get("volume")]

    rally_avg = sum(rally_vols) / len(rally_vols) if rally_vols else 0
    pullback_avg = sum(pullback_vols) / len(pullback_vols) if pullback_vols else 0

    ratio = pullback_avg / rally_avg if rally_avg > 0 else 0

    if ratio >= VOLUME_STRONG_THRESHOLD:
        quality = "strong"
    elif ratio >= VOLUME_MODERATE_THRESHOLD:
        quality = "moderate"
    else:
        quality = "weak"

    return {
        "rally_avg_volume": round(rally_avg),
        "pullback_avg_volume": round(pullback_avg),
        "current_vs_rally_ratio": round(ratio, 2),
        "bounce_quality": quality,
    }


def _classify(rally: dict, pullback: dict, volume_profile: dict) -> str:
    """Classify price action scenario."""
    if not rally:
        return "NORMAL"

    above_base = pullback["above_base_pct"]
    retracement = pullback["retracement_pct"]
    quality = volume_profile["bounce_quality"]

    # POST_SPIKE: still elevated + weak volume
    if above_base > POST_SPIKE_ABOVE_BASE_PCT and quality in ("weak", "moderate"):
        return "POST_SPIKE"

    # EXTENDED_PULLBACK: gave back >50% of rally + weak volume
    if retracement > 50 and quality == "weak":
        return "EXTENDED_PULLBACK"

    # BASE_BUILDING: almost fully retraced (back near base)
    if retracement > 80:
        return "BASE_BUILDING"

    # Still elevated but strong volume = healthy pullback
    return "NORMAL"


def _build_risk_flags(
    rally: dict,
    pullback: dict,
    volume_profile: dict,
    gaps: list[dict],
) -> list[str]:
    """Build human-readable risk flags."""
    flags = []
    base_k = rally["pre_rally_zone"]
    rally["peak_price"]

    if pullback["above_base_pct"] > 5:
        flags.append(
            f"Stock +{pullback['above_base_pct']:.0f}% above pre-spike base ({base_k:.1f}k)"
        )

    if pullback["gap_fill_risk"]:
        lo, hi = pullback["fib_fill_zone"]
        flags.append(f"Gap fill risk to {lo:.1f}k-{hi:.1f}k zone")

    if volume_profile["bounce_quality"] == "weak":
        ratio = volume_profile["current_vs_rally_ratio"]
        flags.append(f"Weak volume ({ratio:.2f}x rally average)")

    if gaps:
        unfilled = [g for g in gaps if g["type"] == "gap_up"]
        if unfilled:
            prices = ", ".join(f"{g['gap_low']:.1f}k" for g in unfilled[:2])
            flags.append(f"Unfilled gap(s) at {prices}")

    return flags


# ---------------------------------------------------------------------------
# Prose Formatting
# ---------------------------------------------------------------------------


def format_price_action_prose(pa: dict) -> str:
    """Format price action dict as natural language for LLM agents."""
    classification = pa.get("classification", "NORMAL")
    if classification == "NORMAL":
        # Only mention unfilled gaps if present
        gaps = pa.get("gaps", [])
        if gaps:
            gap_str = ", ".join(f"{g['gap_low']:.1f}k ({g['date']})" for g in gaps[:2])
            return f"Price Action: NORMAL. Unfilled gap(s) at {gap_str}."
        return ""

    rally = pa["rally"]
    pullback = pa["pullback"]
    vol = pa["volume_profile"]

    base_k = rally["pre_rally_zone"]
    peak_k = rally["peak_price"]
    sessions = rally["gain_sessions"]
    gain = rally["gain_pct"]

    parts = [
        f"Price Action (30d): {classification} — "
        f"+{gain:.0f}% in {sessions} sessions "
        f"({base_k:.1f}k→{peak_k:.1f}k, {rally['base_date']}→{rally['peak_date']})."
    ]

    parts.append(
        f"Pullback: {pullback['from_peak_pct']:+.1f}% from peak, "
        f"+{pullback['above_base_pct']:.0f}% above base. "
        f"Retracement {pullback['retracement_pct']:.0f}%."
    )

    lo, hi = pullback["fib_fill_zone"]
    parts.append(f"Fib fill zone: {lo:.1f}k-{hi:.1f}k.")

    parts.append(
        f"Volume: {vol['current_vs_rally_ratio']:.2f}x rally avg "
        f"({vol['bounce_quality'].upper()} bounce)."
    )

    flags = pa.get("risk_flags", [])
    if flags:
        parts.append("Risks: " + "; ".join(flags) + ".")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Async Orchestrator (called from get_ticker_data_async)
# ---------------------------------------------------------------------------


async def get_price_action_context(
    ticker: str,
    scan_date: date | None = None,
    current_close: float = 0,
    days: int = 30,
) -> dict | None:
    """Fetch price history via vnstock API and compute price action metrics.

    Args:
        ticker: Stock ticker (e.g., 'VCB')
        scan_date: Reference date (defaults to today)
        current_close: Current close in raw VND
        days: Trading days to analyze (default 30)

    Returns:
        Price action dict or None if insufficient data.
    """
    from shared.vnstock_client import fetch_history

    if scan_date is None:
        scan_date = date.today()

    # Buffer for weekends/holidays
    start = (scan_date - timedelta(days=days + 15)).strftime("%Y-%m-%d")
    end = scan_date.strftime("%Y-%m-%d")

    try:
        result = await fetch_history(symbol=ticker.upper(), start=start, end=end)
        if "error" in result:
            return None

        candles = result.get("data", [])
        # Take last N trading days
        candles = candles[-days:] if len(candles) > days else candles
        if len(candles) < 10:
            return None

        return analyze_price_action(candles, current_close)

    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_date(candle: dict) -> str:
    """Extract date string from candle."""
    t = candle.get("time", "")
    return str(t)[:10] if t else ""
