"""
Sell-off pattern detection for dip-buy setups.

Deterministic Python — no LLM. Mirrors price_action.py (rally detection)
but detects multi-day sell-offs with volume climax into oversold support.

Used by alert_registrar to create multi-tranche dip-buy alerts when morning
brief identifies a BOUNCE strategy pick with an active sell-off setup.
"""

from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

CAPITULATION_VOL_MULTIPLIER = 4.0  # Volume > 4x 20d SMA
CAPITULATION_RSI_MAX = 30.0  # RSI < 30
CAPITULATION_MIN_RED_DAYS = 3  # 3+ consecutive red candles

EXHAUSTION_VOL_MULTIPLIER = 2.5  # Volume > 2.5x 20d SMA
EXHAUSTION_RSI_MAX = 35.0  # RSI < 35
EXHAUSTION_MIN_RED_DAYS = 2  # 2+ consecutive red candles

LOOKBACK_DAYS = 15  # Candles to fetch for analysis


# ---------------------------------------------------------------------------
# Core Detection
# ---------------------------------------------------------------------------


def _count_consecutive_red(candles: list[dict]) -> int:
    """Count consecutive red candles from the most recent bar backwards."""
    count = 0
    for c in reversed(candles):
        if c.get("close", 0) < c.get("open", 0):
            count += 1
        else:
            break
    return count


def _compute_volume_sma(candles: list[dict], periods: int = 20) -> float:
    """Compute average volume over last N candles (excluding current day)."""
    vols = [c.get("volume", 0) for c in candles[:-1] if c.get("volume")]
    if not vols:
        return 0.0
    return sum(vols[-periods:]) / min(len(vols), periods)


def _classify_setup(
    consecutive_red: int,
    vol_ratio: float,
    rsi: float,
) -> tuple[str, str] | None:
    """Classify sell-off type and conviction. Returns (type, conviction) or None."""
    if (
        consecutive_red >= CAPITULATION_MIN_RED_DAYS
        and vol_ratio >= CAPITULATION_VOL_MULTIPLIER
        and rsi <= CAPITULATION_RSI_MAX
    ):
        return "CAPITULATION", "HIGH"

    if (
        consecutive_red >= EXHAUSTION_MIN_RED_DAYS
        and vol_ratio >= EXHAUSTION_VOL_MULTIPLIER
        and rsi <= EXHAUSTION_RSI_MAX
    ):
        conviction = "HIGH" if vol_ratio >= 3.5 else "MEDIUM"
        return "EXHAUSTION", conviction

    if consecutive_red >= EXHAUSTION_MIN_RED_DAYS:
        return "ORDERLY_DECLINE", "LOW"

    return None


def _build_tranche_zones(technicals: dict) -> list[dict]:
    """Build two entry zones from technicals support levels.

    technicals is the full dict from get_ticker_data_async() — support levels
    are nested under technicals["levels"], not at the top level.
    """
    zones = []
    levels = technicals.get("levels") or {}

    # Zone 1: nearest_support or range_20d_low (more aggressive)
    zone1_price = levels.get("nearest_support") or levels.get("range_20d_low")
    if zone1_price:
        zones.append(
            {
                "zone": 1,
                "price": float(zone1_price),
                "pct_of_size": 50,
                "rationale": "nearest support / 20d range low",
            }
        )

    # Zone 2: swing_low (deeper, more conservative)
    zone2_price = levels.get("swing_low")
    if zone2_price and (not zone1_price or float(zone2_price) < float(zone1_price) * 0.98):
        zones.append(
            {
                "zone": 2,
                "price": float(zone2_price),
                "pct_of_size": 50,
                "rationale": "swing low / historical floor",
            }
        )

    return zones


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def detect_selloff_setup(ticker: str, scan_date: date | None = None) -> dict | None:
    """Detect multi-day sell-off pattern for dip-buy setup.

    Args:
        ticker: Stock ticker (e.g. 'FPT')
        scan_date: Reference date (default: today)

    Returns:
        Dict with classification, conviction, tranche_zones, and context,
        or None if no sell-off setup detected.
    """
    from shared.vnstock_client import fetch_history

    if scan_date is None:
        scan_date = date.today()

    # Fetch recent candles
    start = (scan_date - timedelta(days=LOOKBACK_DAYS + 10)).strftime("%Y-%m-%d")
    end = scan_date.strftime("%Y-%m-%d")

    try:
        result = await fetch_history(symbol=ticker.upper(), start=start, end=end)
        if "error" in result:
            return None
        candles = result.get("data", [])
        candles = candles[-(LOOKBACK_DAYS):] if len(candles) > LOOKBACK_DAYS else candles
        if len(candles) < 5:
            return None
    except Exception:
        return None

    # Compute sell-off metrics
    consecutive_red = _count_consecutive_red(candles)
    vol_sma = _compute_volume_sma(candles)
    current_vol = candles[-1].get("volume", 0) or 0
    vol_ratio = current_vol / vol_sma if vol_sma > 0 else 0.0

    # Get RSI + support levels from technicals
    rsi = 50.0
    technicals: dict = {}
    try:
        from agents.tools.technicals import get_ticker_data_async

        tech = await get_ticker_data_async(ticker)
        if tech and "error" not in tech:
            rsi = float(tech.get("rsi") or 50.0)
            technicals = tech
    except Exception:
        pass

    # Classify
    classification = _classify_setup(consecutive_red, vol_ratio, rsi)
    if not classification:
        return None

    setup_type, conviction = classification

    # Get tranche zones
    tranche_zones = _build_tranche_zones(technicals)
    if not tranche_zones:
        return None  # No actionable support levels

    # Get foreign flow (non-fatal if unavailable)
    foreign_net_b = None
    try:
        from agents.tools.enrichment import get_ticker_flow_async

        flow = await get_ticker_flow_async(ticker, scan_date)
        if flow and "error" not in flow:
            foreign_net = flow.get("foreign_net")
            if foreign_net is not None:
                foreign_net_b = round(float(foreign_net) / 1e9, 1)
    except Exception:
        pass

    return {
        "ticker": ticker.upper(),
        "classification": setup_type,
        "conviction": conviction,
        "consecutive_red_days": consecutive_red,
        "volume_profile": {
            "current_vol": int(current_vol),
            "vol_sma20": round(vol_sma),
            "ratio": round(vol_ratio, 1),
        },
        "rsi": round(rsi, 1),
        "tranche_zones": tranche_zones,
        "foreign_net_b": foreign_net_b,  # billion VND, negative = net selling
    }
