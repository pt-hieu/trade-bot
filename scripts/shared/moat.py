"""Deterministic moat scoring from qualitative dimension ratings.

LLM provides dimension ratings (STRONG/MODERATE/WEAK/NONE),
Python computes the score and overall classification.
"""

DIMENSION_SCORES: dict[str, int] = {"STRONG": 25, "MODERATE": 15, "WEAK": 5, "NONE": 0}
VIETNAM_FACTOR_BONUS = 5  # per flag


def score_moat_from_ratings(assessment: dict) -> int:
    """Compute 0-100 moat score from qualitative ratings.

    Dimensions: network_effects, switching_costs, scale_economies, intangible_assets
    Vietnam factors: fol_premium, state_ownership, regulatory_license (+5 each, max +15)
    """
    dimension_keys = ("network_effects", "switching_costs", "scale_economies", "intangible_assets")
    vietnam_keys = ("fol_premium", "state_ownership", "regulatory_license")

    dimension_total = sum(
        DIMENSION_SCORES.get(str(assessment.get(k, "NONE")).upper(), 0) for k in dimension_keys
    )
    # Max dimension score = 4 * 25 = 100; normalise to 85 pts max, vietnam adds up to 15
    # Use direct sum capped at 85 then add vietnam bonus (keeps range 0-100)
    dimension_score = min(dimension_total, 85)

    vietnam_bonus = sum(VIETNAM_FACTOR_BONUS for k in vietnam_keys if assessment.get(k) is True)
    vietnam_bonus = min(vietnam_bonus, 15)

    return dimension_score + vietnam_bonus


def classify_overall_moat(score: int) -> str:
    """WIDE (>=60), NARROW (30-59), NONE (<30)."""
    if score >= 60:
        return "WIDE"
    if score >= 30:
        return "NARROW"
    return "NONE"


def compute_quantitative_moat_signals(ratios_list: list[dict]) -> dict:
    """Extract quantitative signals that support moat assessment.

    Returns evidence dict for LLM to reference in ratings.
    Does NOT assign moat ratings — that's the LLM's job.

    Examples:
    - "consistent_high_roe": True if ROE > 15% for 3+ consecutive quarters
    - "stable_margins": True if net margin variance < 2pp over 4Q
    - "margin_trend": "IMPROVING" | "STABLE" | "DECLINING"
    - "roe_trend": "IMPROVING" | "STABLE" | "DECLINING"
    """
    if not ratios_list:
        return {}

    # Most recent first — values already whole % from shared/api normalization (rule 18)
    roe_values = [
        _to_pct(r.get("roe"), is_roe=True) for r in ratios_list if r.get("roe") is not None
    ]
    margin_values = [
        _to_pct(r.get("net_margin"), is_roe=False)
        for r in ratios_list
        if r.get("net_margin") is not None
    ]
    roe_values = [v for v in roe_values if v is not None]
    margin_values = [v for v in margin_values if v is not None]

    signals: dict = {}

    # Consistent high ROE: 3+ consecutive quarters above 15%
    if len(roe_values) >= 3:
        signals["consistent_high_roe"] = all(v > 15.0 for v in roe_values[:3])
    else:
        signals["consistent_high_roe"] = False

    # Stable margins: variance < 2pp over last 4 quarters (values are in pct units)
    if len(margin_values) >= 4:
        recent = margin_values[:4]
        margin_range = max(recent) - min(recent)
        signals["stable_margins"] = margin_range < 2.0
    else:
        signals["stable_margins"] = None

    # Margin trend (compare avg of newest 2 vs oldest 2 of up to 4 quarters)
    signals["margin_trend"] = _compute_trend(margin_values)

    # ROE trend
    signals["roe_trend"] = _compute_trend(roe_values)

    return signals


def _to_pct(value, *, is_roe: bool) -> float | None:
    """Return value as whole-number % (already normalized by shared/api, rule 18)."""
    return value


def _compute_trend(values: list[float]) -> str:
    """IMPROVING | STABLE | DECLINING from a list of values (newest first)."""
    if len(values) < 4:
        return "STABLE"
    newest_avg = (values[0] + values[1]) / 2
    oldest_avg = (values[2] + values[3]) / 2
    delta = newest_avg - oldest_avg
    if delta > 1.5:
        return "IMPROVING"
    if delta < -1.5:
        return "DECLINING"
    return "STABLE"
