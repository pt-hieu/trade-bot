"""Portfolio correlation check for sector concentration warnings."""

from shared.neon.portfolio import get_holdings_with_sectors
from shared.trading_config import get_trading_config

# Cluster mapping for Vietnamese market sectors
_CLUSTER_MAP = {
    "Real Estate": "property-financial",
    "Banking": "property-financial",
    "Financial": "property-financial",
    "Insurance": "property-financial",
    "Securities": "property-financial",
    "Technology": "tech-growth",
}
_DEFAULT_CLUSTER = "commodity-industrial"


async def get_holdings_sectors_async() -> list[dict]:
    """Get current holdings with sector info from DB.

    Returns list of dicts with ticker, plan_type, sector.
    """
    return await get_holdings_with_sectors()


def compute_portfolio_correlation(holdings: list[dict]) -> dict:
    """Compute sector cluster concentration from holdings.

    Args:
        holdings: List of dicts with ticker, plan_type, sector.

    Returns:
        Dict with level (HIGH/MEDIUM/LOW), dominant_cluster, note,
        diversification_advice.
    """
    if not holdings:
        return {
            "level": "LOW",
            "dominant_cluster": None,
            "note": "No active holdings",
            "diversification_advice": None,
        }

    # Map each holding to cluster
    cluster_counts: dict[str, list[str]] = {}
    for h in holdings:
        sector = h.get("sector", "Unknown")
        cluster = _CLUSTER_MAP.get(sector, _DEFAULT_CLUSTER)
        cluster_counts.setdefault(cluster, []).append(h["ticker"])

    total = len(holdings)
    dominant_cluster = max(cluster_counts, key=lambda c: len(cluster_counts[c]))
    dominant_count = len(cluster_counts[dominant_cluster])
    concentration = dominant_count / total if total > 0 else 0

    cfg = get_trading_config()
    high_threshold = cfg.sector_concentration_high_pct / 100
    med_threshold = cfg.sector_concentration_med_pct / 100

    if concentration > high_threshold:
        level = "HIGH"
    elif concentration > med_threshold:
        level = "MEDIUM"
    else:
        level = "LOW"

    # Build advice
    advice = None
    if level in ("HIGH", "MEDIUM"):
        missing = [
            c
            for c in ["tech-growth", "property-financial", "commodity-industrial"]
            if c != dominant_cluster and c not in cluster_counts
        ]
        if missing:
            advice = f"Next entry should target {missing[0].replace('-', '/')}"
        else:
            underweight = min(cluster_counts, key=lambda c: len(cluster_counts[c]))
            if underweight != dominant_cluster:
                advice = f"Consider adding {underweight.replace('-', '/')} exposure"

    tickers = ", ".join(cluster_counts[dominant_cluster])
    note = f"{dominant_count}/{total} positions in {dominant_cluster} cluster ({tickers})"

    return {
        "level": level,
        "dominant_cluster": dominant_cluster,
        "note": note,
        "diversification_advice": advice,
    }
