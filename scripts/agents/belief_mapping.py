"""Confidence-to-conviction mapping — single choke point for the three-scale problem.

Three confidence scales exist in the system:
  1. Sub-analysts: int 1-10 (SectorAnalystView.confidence)
  2. Aggregated signals: Literal["HIGH", "MEDIUM", "LOW"] (TickerSignal.confidence)
  3. Beliefs: float 0.0-1.0 (TickerBelief.conviction)

This module maps them all to a single 0.0-1.0 conviction score for deterministic use.
"""

# Signal confidence → conviction mapping
_SIGNAL_CONFIDENCE_MAP: dict[str | None, float] = {
    "HIGH": 0.8,
    "MEDIUM": 0.5,
    "LOW": 0.3,
    None: 0.5,
}


def map_signal_confidence_to_conviction(
    signal_confidence: str | None,
    aggregated_belief: dict | None = None,
) -> float:
    """Map multi-scale confidence to a single 0.0-1.0 conviction score.

    Priority: aggregated_belief.conviction (if exists and non-zero) > signal_confidence.

    Args:
        signal_confidence: HIGH/MEDIUM/LOW from TickerSignal
        aggregated_belief: from get_latest_aggregated_beliefs() — has conviction field

    Returns:
        float 0.0-1.0 conviction score
    """
    if aggregated_belief:
        belief_conviction = float(aggregated_belief.get("conviction") or 0)
        if belief_conviction > 0:
            return belief_conviction

    return _SIGNAL_CONFIDENCE_MAP.get(signal_confidence, 0.5)
