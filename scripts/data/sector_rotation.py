"""
Sector rotation detection using GLM analysis.

Supports regime-aware rotation:
- In RISK_OFF: Defensive sectors (state_owned/energy) are HOT, growth sectors are COLD
- In RISK_ON: High-momentum sectors are HOT, laggards are COLD
- In NEUTRAL: Traditional RSI-based rotation
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from shared.llm import call_llm_with_json_parse

SECTOR_ROTATION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "sector_rotation",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "hot_sectors": {"type": "array", "items": {"type": "string"}},
                "cold_sectors": {"type": "array", "items": {"type": "string"}},
                "rotation_signal": {"type": "string"},
                "reasoning": {"type": "string"},
            },
            "required": ["hot_sectors", "cold_sectors", "rotation_signal", "reasoning"],
            "additionalProperties": False,
        },
    },
}


# Sector classification for regime-aware rotation
DEFENSIVE_SECTORS = ["state_owned"]  # GAS, PLX, POW, GVR, BVH - energy/utilities
GROWTH_SECTORS = ["technology", "real_estate", "banking"]  # High-beta, growth-oriented
CYCLICAL_SECTORS = ["consumer", "infrastructure"]  # Economic cycle dependent


# Sector mapping for all known stocks
SECTOR_MAP = {
    # Banking
    "ACB": "banking",
    "BID": "banking",
    "CTG": "banking",
    "HDB": "banking",
    "MBB": "banking",
    "SHB": "banking",
    "STB": "banking",
    "TCB": "banking",
    "TPB": "banking",
    "VCB": "banking",
    "VIB": "banking",
    "VPB": "banking",
    # Real Estate
    "BCM": "real_estate",
    "NLG": "real_estate",
    "VHM": "real_estate",
    "VRE": "real_estate",
    "KBC": "real_estate",
    "IDC": "real_estate",
    "KDH": "real_estate",
    "DXS": "infrastructure",
    # Technology / Securities
    "FPT": "technology",
    "SSI": "securities",
    "VIX": "technology",
    "MWG": "consumer",
    # Consumer
    "MSN": "consumer",
    "SAB": "consumer",
    "VNM": "consumer",
    "VIC": "consumer",
    # State-Owned
    "GAS": "state_owned",
    "GVR": "state_owned",
    "PLX": "state_owned",
    "POW": "state_owned",
    "BVH": "state_owned",
    "HVN": "state_owned",
    # Infrastructure
    "HPG": "infrastructure",
    "PVT": "infrastructure",
    "PVI": "infrastructure",
    "SZC": "infrastructure",
}


async def get_previous_day_data() -> dict:
    """Load previous day's technicals from database.

    Returns:
        Dict of ticker -> technical data
    """
    from shared.api.technicals import get_technicals
    from shared.neon import get_swing_watchlist

    watchlist = await get_swing_watchlist()
    tickers = [t for sector_tickers in watchlist.values() for t in sector_tickers]
    if tickers:
        data = await get_technicals(tickers)
        if data:
            return data

    return {}


def detect_rotation(
    technicals: dict, market_regime: str = "NEUTRAL", rotation_history: str = ""
) -> dict:
    """
    Detect hot/cold sectors based on RSI distribution and market regime.

    In RISK_OFF regime:
    - Defensive sectors (state_owned/energy) become HOT regardless of RSI
    - Growth sectors become COLD even if technically strong
    - Safe haven rotation takes priority

    In RISK_ON regime:
    - High-momentum growth sectors are HOT
    - Defensive sectors with high RSI may continue (momentum)

    In NEUTRAL regime:
    - Traditional RSI-based rotation applies

    Args:
        technicals: Dict of ticker -> technical data
        market_regime: RISK_ON, RISK_OFF, or NEUTRAL

    Returns:
        Dict with hot_sectors, cold_sectors, rotation_signal, reasoning
    """
    # Group RSI by sector
    sector_rsi = {}
    for ticker, tech in technicals.items():
        sector = SECTOR_MAP.get(ticker, "other")
        if sector == "other":
            continue
        if sector not in sector_rsi:
            sector_rsi[sector] = []
        if tech.get("rsi"):
            sector_rsi[sector].append(tech["rsi"])

    # Calculate sector averages
    sector_stats = {}
    for sector, rsis in sector_rsi.items():
        if rsis:
            avg = sum(rsis) / len(rsis)
            # Count stocks in buy zone (RSI 30-50)
            buy_zone = sum(1 for r in rsis if 30 <= r <= 50)
            oversold = sum(1 for r in rsis if r < 30)
            overbought = sum(1 for r in rsis if r > 70)
            sector_stats[sector] = {
                "avg_rsi": round(avg, 1),
                "buy_zone_count": buy_zone,
                "oversold_count": oversold,
                "overbought_count": overbought,
                "total": len(rsis),
                "type": "defensive"
                if sector in DEFENSIVE_SECTORS
                else "growth"
                if sector in GROWTH_SECTORS
                else "cyclical",
            }

    # Build regime-aware prompt
    regime_context = _get_regime_context(market_regime)

    prompt = f"""Analyze sector rotation for Vietnamese stock market.

MARKET REGIME: {market_regime}
{regime_context}
{rotation_history}
SECTOR RSI DATA:
{json.dumps(sector_stats, indent=2)}

SECTOR CLASSIFICATIONS:
- Defensive (safe haven): {DEFENSIVE_SECTORS} - GAS, PLX, POW, GVR, BVH
- Growth (high beta): {GROWTH_SECTORS} - FPT, TCB, VHM, NLG, etc.
- Cyclical: {CYCLICAL_SECTORS} - MSN, HPG, etc.

REGIME-AWARE RULES:
1. In RISK_OFF regime:
   - Defensive sectors are HOT (safe haven demand) even if overbought
   - Growth sectors are COLD (sell pressure) even if technically strong
   - Do NOT recommend buying growth stocks

2. In RISK_ON regime:
   - High-momentum growth sectors are HOT
   - Overbought can continue in strong trends
   - Defensive sectors may lag

3. In NEUTRAL regime:
   - Traditional RSI-based rotation
   - Hot = stocks in RSI 30-50 (buy zone), oversold recovering
   - Cold = stocks RSI >70 extended without momentum

Use lowercase sector names: banking, real_estate, technology, state_owned, consumer, infrastructure

Output:
- hot_sectors: Array of sector names to favor (max 3)
- cold_sectors: Array of sector names to avoid (max 3)
- rotation_signal: One sentence describing the rotation trade considering the regime
- reasoning: 2-3 sentences explaining why, with explicit regime consideration"""

    try:
        result = call_llm_with_json_parse(
            "You analyze sector rotation signals for Vietnamese stocks.",
            prompt,
            json_schema=SECTOR_ROTATION_SCHEMA,
        )
        result["market_regime"] = market_regime
        return result
    except Exception as e:
        raise RuntimeError(f"Sector rotation LLM failed: {e}") from e


def _get_regime_context(market_regime: str) -> str:
    """Get regime-specific context for the prompt."""
    if market_regime == "RISK_OFF":
        return """
REGIME CONTEXT: Market is in RISK_OFF mode (overbought, correction expected).
- CRITICAL: Defensive sectors (state_owned with GAS, PLX) should be marked HOT as safe havens
- CRITICAL: Growth sectors (technology, banking, real_estate) should be marked COLD
- Even if a defensive sector has high RSI, it is HOT because money flows to safety
- This is a DEFENSIVE rotation, not a momentum rotation"""
    elif market_regime == "RISK_ON":
        return """
REGIME CONTEXT: Market is in RISK_ON mode (bullish momentum, risk appetite high).
- Growth sectors with momentum should be HOT
- Overbought growth stocks may continue in strong trends
- Defensive sectors may underperform"""
    else:
        return """
REGIME CONTEXT: Market is NEUTRAL (mixed signals).
- Use traditional RSI-based rotation
- Favor stocks in buy zone (RSI 30-50)
- Avoid extended overbought without clear momentum"""


def _rule_based_rotation(sector_stats: dict, market_regime: str) -> dict:
    """Fallback rule-based sector rotation."""
    hot = []
    cold = []

    if market_regime == "RISK_OFF":
        # In RISK_OFF, defensive is hot, growth is cold
        for sector, _stats in sector_stats.items():
            if sector in DEFENSIVE_SECTORS:
                hot.append(sector)
            elif sector in GROWTH_SECTORS:
                cold.append(sector)
        return {
            "hot_sectors": hot[:3],
            "cold_sectors": cold[:3],
            "rotation_signal": "Defensive rotation - favor state_owned (GAS, PLX) as safe havens",
            "reasoning": "RISK_OFF regime detected. Money flows to defensive sectors regardless of RSI.",
            "market_regime": market_regime,
        }

    # RISK_ON or NEUTRAL - use RSI-based logic
    for sector, stats in sector_stats.items():
        if stats["buy_zone_count"] > 0 or stats["oversold_count"] > 0:
            hot.append(sector)
        elif stats["overbought_count"] >= 2 and sector in GROWTH_SECTORS:
            cold.append(sector)

    return {
        "hot_sectors": hot[:3],
        "cold_sectors": cold[:3],
        "rotation_signal": "RSI-based rotation - favor buy zone stocks",
        "reasoning": "Traditional rotation based on RSI distribution.",
        "market_regime": market_regime,
    }


async def run_sector_rotation(
    research_dir: Path,
    output_dir: Path,
    market_regime: str = "NEUTRAL",
) -> dict:
    """
    Run full sector rotation detection with regime awareness.

    Args:
        research_dir: Root research directory (for previous day data)
        output_dir: Today's output directory
        market_regime: RISK_ON, RISK_OFF, or NEUTRAL from market_level analysis

    Returns:
        Sector rotation result dict
    """
    print("Loading previous day's technicals...")
    technicals = await get_previous_day_data()

    if not technicals:
        print("WARNING: No previous day data found, skipping rotation detection")
        result = {
            "hot_sectors": [],
            "cold_sectors": [],
            "rotation_signal": "No data available",
            "reasoning": "Previous day scan data not found",
            "market_regime": market_regime,
        }
    else:
        print(f"  Loaded {len(technicals)} stocks")
        print(f"  Market regime: {market_regime}")

        # Load rotation history for prompt context
        rotation_history = await _load_rotation_history_summary()
        if rotation_history:
            print("  Loaded rotation history for calibration")

        print("\nDetecting sector rotation via GLM...")
        result = detect_rotation(technicals, market_regime, rotation_history)

    return result


async def _load_rotation_history_summary() -> str:
    """Load rotation history from database and format for prompt injection.

    Returns:
        Formatted string with rotation accuracy summary, or empty string if no data.
    """
    try:
        from shared.neon import get_rotation_patterns

        rotation = await get_rotation_patterns()

        if not rotation or rotation.get("total_days", 0) == 0:
            return ""

        # Format sector scores
        sector_scores = rotation.get("sector_scores", {})
        sector_lines = []
        for sector, scores in sector_scores.items():
            hot_acc = scores.get("as_hot", 0)
            cold_acc = scores.get("as_cold", 0)
            sector_lines.append(f"- {sector}: as HOT {hot_acc:.0%}, as COLD {cold_acc:.0%}")

        summary = f"""
HISTORICAL ROTATION ACCURACY (last {rotation.get("total_days", 0)} days):
- Overall accuracy: {rotation.get("overall_accuracy", 0):.0%}
- Hot hit rate: {rotation.get("hot_hit_rate", 0):.0%}
- Cold hit rate: {rotation.get("cold_hit_rate", 0):.0%}
- Avg hot vs market: {rotation.get("avg_hot_vs_market", 0):+.2f}%
- Avg cold vs market: {rotation.get("avg_cold_vs_market", 0):+.2f}%

PER-SECTOR ACCURACY:
{chr(10).join(sector_lines)}

Use this history to calibrate your predictions. Trust signals that have been accurate historically."""

        return summary
    except Exception as e:
        logger.warning("get_rotation_accuracy_context failed: %s", e)
        return ""
