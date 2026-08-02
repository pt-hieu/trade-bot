"""
Macro regime evaluation for retrospective analysis.

Evaluates if global risk regime predictions matched VN market outcomes.
"""

import logging
import re
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)


async def evaluate_macro_for_day(
    scan_date: date, eod_prices: dict | None = None, date_dir: Path | None = None
) -> dict | None:
    """Evaluate if macro regime prediction matched VN market outcome.

    Args:
        scan_date: Date to evaluate
        eod_prices: End-of-day prices dict (ticker -> {close, change_pct, ...})
        date_dir: Path to research/YYYY-MM-DD/ (for morning brief parsing)

    Returns:
        Evaluation dict or None if no macro data available
    """
    from shared.neon import get_macro_metrics

    macro = await get_macro_metrics(scan_date)
    if "error" in macro:
        return None

    regime = macro.get("global_risk_regime") or "CAUTIOUS"
    dxy_value = macro.get("dxy_value")
    vix_value = macro.get("vix_value")

    # Data quality guard: skip scoring when macro inputs are clearly stale/missing
    stale_data = vix_value == 0 and dxy_value == 0

    # Get VN-Index change estimate
    vn_change = _estimate_vn_index_change(eod_prices)

    # Check foreign flow alignment (still uses morning brief file)
    foreign_aligned = _check_foreign_flow_alignment(date_dir, regime) if date_dir else None

    # Check recommendation compliance with regime (still uses morning brief file)
    compliance = _check_recommendation_compliance(date_dir, regime) if date_dir else None

    return {
        "global_risk_regime": regime,
        "dxy_value": dxy_value,
        "vix_value": vix_value,
        "vn_index_change_pct": vn_change,
        "regime_appropriate": None if stale_data else _evaluate_regime_accuracy(regime, vn_change),
        "foreign_flow_aligned": foreign_aligned,
        "recommendation_compliance": compliance,
        "data_quality": "STALE" if stale_data else "OK",
    }


def _estimate_vn_index_change(eod_prices: dict | None) -> float | None:
    """Estimate VN-Index daily change from large cap proxies.

    Uses weighted average of major stocks (VCB, VHM, FPT, VIC, TCB) as VN-Index proxy.
    """
    if not eod_prices:
        return None

    # Large cap proxies with approximate VN-Index weight
    proxies = {
        "VCB": 0.25,  # ~10% of VN-Index
        "VHM": 0.20,  # ~8%
        "FPT": 0.15,  # ~6%
        "VIC": 0.15,  # ~6%
        "TCB": 0.15,  # ~5%
        "BID": 0.10,  # ~4%
    }

    weighted_sum = 0.0
    weight_total = 0.0

    for ticker, weight in proxies.items():
        if ticker in eod_prices:
            change_pct = eod_prices[ticker].get("change_pct")
            if change_pct is not None:
                weighted_sum += change_pct * weight
                weight_total += weight

    if weight_total > 0:
        return round(weighted_sum / weight_total, 2)

    return None


def _evaluate_regime_accuracy(regime: str, vn_change: float | None) -> bool | None:
    """Check if regime prediction matched market outcome.

    Logic (asymmetric — caution is cheap, recklessness is expensive):
    - CALM: correct if market >= -0.5% (no significant drop)
    - CAUTIOUS: correct if market < +1.0% (caution warranted unless strong rally)
    - ELEVATED: correct if market < 0% (market went down)
    - CRISIS: correct if market < -1.5% (market crashed)
    """
    if vn_change is None:
        return None

    if regime == "CALM":  # noqa: SIM116
        # CALM prediction is correct if market didn't drop significantly
        return vn_change >= -0.5
    elif regime == "CAUTIOUS":
        # CAUTIOUS = "risks present, be careful". Correct unless market rallied strongly,
        # proving caution was unwarranted. Asymmetric: cost of unnecessary caution (missed
        # upside) < cost of insufficient caution (losses).
        return vn_change < 1.0
    elif regime == "ELEVATED":
        # ELEVATED is correct if market went down
        return vn_change < 0
    elif regime == "CRISIS":
        # CRISIS is correct if market crashed
        return vn_change < -1.5

    return None


def _check_foreign_flow_alignment(date_dir: Path, regime: str) -> bool | None:
    """Check if foreign flow aligned with regime prediction.

    CAUTIOUS/ELEVATED/CRISIS should see foreign net selling.
    CALM should see neutral or net buying.
    """
    # Try to parse foreign flow from morning brief
    brief_file = date_dir / "morning-brief.md"
    if not brief_file.exists():
        return None

    try:
        content = brief_file.read_text(encoding="utf-8")
    except Exception:
        logger.warning("Failed to read morning brief for foreign flow: %s", brief_file)
        return None

    # Look for foreign flow mentions (simple heuristic)
    content_lower = content.lower()

    # Detect foreign selling signals
    foreign_selling = any(
        phrase in content_lower
        for phrase in [
            "foreign sell",
            "foreign net sell",
            "net sold",
            "foreigners sold",
            "foreign outflow",
        ]
    )

    # Detect foreign buying signals
    foreign_buying = any(
        phrase in content_lower
        for phrase in [
            "foreign buy",
            "foreign net buy",
            "net bought",
            "foreigners bought",
            "foreign inflow",
        ]
    )

    # CAUTIOUS/ELEVATED/CRISIS should align with selling
    if regime in ("CAUTIOUS", "ELEVATED", "CRISIS"):
        if foreign_selling:
            return True
        if foreign_buying:
            return False
        return None  # No clear signal

    # CALM should align with buying or neutral
    if regime == "CALM":
        if foreign_buying:
            return True
        if foreign_selling:
            return False
        return None

    return None


def _check_recommendation_compliance(date_dir: Path, regime: str) -> float | None:
    """Check what % of recommendations respected the regime.

    In ELEVATED/CRISIS regime, should NOT have aggressive BUY recs.
    In CAUTIOUS, BUY recs should be defensive or reduced size.
    """
    brief_file = date_dir / "morning-brief.md"
    if not brief_file.exists():
        return None

    try:
        content = brief_file.read_text(encoding="utf-8")
    except Exception:
        logger.warning("Failed to read morning brief for compliance: %s", brief_file)
        return None

    # Count aggressive vs appropriate recommendations
    # Look for TOP PICKS section
    top_picks_match = re.search(
        r"TOP PICKS\n(.*?)(?=\n[A-Z]{2,}|\Z)",
        content,
        re.DOTALL | re.IGNORECASE,
    )

    if not top_picks_match:
        return None

    top_picks_content = top_picks_match.group(1)

    # Count BUY recommendations
    buy_count = len(re.findall(r"\bBUY\b", top_picks_content, re.IGNORECASE))

    # Count defensive/cautious mentions
    defensive_count = len(
        re.findall(
            r"\b(defensive|cautious|reduced|smaller|tight stop|wait)\b",
            top_picks_content,
            re.IGNORECASE,
        )
    )

    # No recommendations = 100% compliance (correctly avoided)
    if buy_count == 0:
        return 1.0 if regime in ("ELEVATED", "CRISIS") else None

    # Calculate compliance based on regime
    if regime == "CALM":
        # CALM: all BUY recs are fine
        return 1.0
    elif regime == "CAUTIOUS":
        # CAUTIOUS: defensive mentions should accompany BUYs
        if defensive_count >= buy_count:
            return 1.0
        return round(defensive_count / buy_count, 2) if buy_count > 0 else 1.0
    elif regime in ("ELEVATED", "CRISIS"):
        # ELEVATED/CRISIS: should have NO aggressive BUYs
        # Having BUYs without defensive language = non-compliance
        compliant = max(0, buy_count - (buy_count - defensive_count))
        return round(compliant / buy_count, 2) if buy_count > 0 else 1.0

    return None
