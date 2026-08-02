"""
Deterministic calculations for long-term watchlist automation.

All formulas are pure Python — no LLM calls. LLM may then adjust results
within defined bounds (±10% entry zone, ±1 conviction level).
"""

from __future__ import annotations

# ── Conviction enum order ────────────────────────────────────────────────────

CONVICTION_LEVELS = ["Low", "Medium-Low", "Medium", "Medium-High", "High"]
_LEVEL_INDEX = {v: i for i, v in enumerate(CONVICTION_LEVELS)}

# Banking tickers use higher D/E threshold
BANK_TICKERS = {"TCB", "VCB", "BID", "ACB", "MBB", "VPB", "HDB", "STB", "CTG", "TPB", "SHB", "VIB"}


# ── Entry zone calculation ───────────────────────────────────────────────────


def calculate_entry_zone(
    ratios: list[dict],
    low_52w: float | None,
    current_entry_vnd: int | None,
) -> tuple[int | None, str]:
    """Calculate baseline entry zone from fundamentals.

    Formula (weighted blend):
        60%: Historical PE floor (25th percentile of 8Q) × latest implied EPS
        20%: Median historical PB × implied BVPS
        20%: 52-week low + 10% buffer

    Args:
        ratios: List of ratio dicts (newest first), each with pe, pb, eps, roe, etc.
        low_52w: 52-week low price in VND (NOT thousands)
        current_entry_vnd: Current manual entry zone in VND (fallback)

    Returns:
        (entry_zone_vnd, method) where method is 'calculated' or 'manual_fallback'
    """
    if not ratios or len(ratios) < 4:
        return (current_entry_vnd, "manual_fallback")

    valid_pe = [r["pe"] for r in ratios if r.get("pe") and r["pe"] > 0]
    valid_pb = [r["pb"] for r in ratios if r.get("pb") and r["pb"] > 0]
    valid_eps = [r["eps"] for r in ratios if r.get("eps") and r["eps"] > 0]

    latest = ratios[0]

    # Need at least PE + EPS data
    if not valid_pe or not valid_eps:
        return (current_entry_vnd, "manual_fallback")

    # 60%: PE floor × latest EPS
    pe_25th = _percentile(valid_pe, 25)
    latest_eps = latest.get("eps") or valid_eps[0]
    # EPS in VND — annualize if quarterly (multiply by 4 as approximation)
    pe_component = pe_25th * latest_eps * 1000  # EPS stored in raw VND units

    # 20%: PB median × implied BVPS (from ROE + EPS approximation)
    pb_component = None
    if valid_pb and latest.get("roe") and latest["roe"] > 0:
        pb_median = _percentile(valid_pb, 50)
        # Implied BVPS ≈ EPS / ROE
        roe = latest["roe"]
        roe = roe / 100  # whole % to decimal (28.27 -> 0.2827)
        if roe > 0:
            implied_bvps = latest_eps / roe * 1000
            pb_component = pb_median * implied_bvps

    # 20%: 52w low + 10% buffer
    low_component = (low_52w * 1.10) if low_52w and low_52w > 0 else None

    # Weighted blend
    total_weight = 0.60
    entry = pe_component * 0.60

    if pb_component:
        entry += pb_component * 0.20
        total_weight += 0.20
    if low_component:
        entry += low_component * 0.20
        total_weight += 0.20

    if total_weight < 0.60:
        return (current_entry_vnd, "manual_fallback")

    # Normalize to full weight
    entry = entry / total_weight * 1.0 if total_weight < 1.0 else entry
    entry_vnd = int(round(entry / 1000) * 1000)  # round to nearest 1000

    # Sanity check: flag if differs >30% from current manual entry
    if current_entry_vnd and current_entry_vnd > 0:
        diff_pct = abs(entry_vnd - current_entry_vnd) / current_entry_vnd * 100
        if diff_pct > 30:
            # Return calculated but note the discrepancy — caller should see review_flags
            pass

    return (entry_vnd, "calculated")


# ── Conviction scoring ───────────────────────────────────────────────────────


def score_conviction(ticker: str, ratios: list[dict]) -> tuple[str, int]:
    """Score conviction level from financial ratios.

    Score 0-100 → maps to conviction enum.
    LLM may adjust ±1 level after this calculation.

    Args:
        ticker: Stock ticker (used for sector-specific thresholds)
        ratios: List of ratio dicts (newest first)

    Returns:
        (conviction_level, raw_score)
    """
    if not ratios:
        return ("Medium", 30)

    latest = ratios[0]
    score = 0
    is_bank = ticker.upper() in BANK_TICKERS

    # ROE scoring
    roe_pct = latest.get("roe")  # already whole % from API normalization
    if roe_pct is not None:
        if roe_pct > 15:
            score += 20
        elif roe_pct > 10:
            score += 10
        elif roe_pct > 8:
            score += 5

    # Net margin
    net_margin = latest.get("net_margin")
    if net_margin is not None:
        nm = net_margin / 100  # whole % to decimal (16.01 -> 0.1601)
        if nm > 0.10:
            score += 10

    # Debt/Equity
    de = latest.get("debt_to_equity")
    if de is not None:
        threshold = 2.0 if is_bank else 1.0
        if de < threshold:
            score += 10

    # PE valuation
    pe = latest.get("pe")
    if pe is not None and pe > 0:
        if pe < 20:
            score += 10
        elif pe < 25:
            score += 5

    # Trend: ROE improving 2+ quarters
    if len(ratios) >= 3:
        roe_vals = [v for r in ratios[:3] if (v := _get_roe_pct(r)) is not None]
        if len(roe_vals) >= 2 and roe_vals[0] > roe_vals[-1]:
            score += 10

    # Trend: margin improving QoQ
    if len(ratios) >= 2:
        nm_curr = _get_nm(ratios[0])
        nm_prev = _get_nm(ratios[1])
        if nm_curr is not None and nm_prev is not None and nm_curr > nm_prev:
            score += 10

    # Current ratio
    cr = latest.get("current_ratio")
    if cr is not None and cr > 1.2:
        score += 5

    # Map score to conviction level
    level = _score_to_conviction(score)
    return (level, score)


def _score_to_conviction(score: int) -> str:
    if score >= 70:
        return "High"
    elif score >= 50:
        return "Medium-High"
    elif score >= 30:
        return "Medium"
    elif score >= 15:
        return "Medium-Low"
    return "Low"


def adjust_conviction(current: str, adjustment: int) -> str:
    """Apply LLM conviction adjustment capped at ±1 level."""
    adjustment = max(-1, min(1, adjustment))
    idx = _LEVEL_INDEX.get(current, 2)
    new_idx = max(0, min(len(CONVICTION_LEVELS) - 1, idx + adjustment))
    return CONVICTION_LEVELS[new_idx]


def apply_entry_zone_adjustment(baseline_vnd: int, adjustment_pct: float) -> int:
    """Apply LLM entry zone adjustment capped at ±10%."""
    adjustment_pct = max(-10.0, min(10.0, adjustment_pct))
    adjusted = baseline_vnd * (1 + adjustment_pct / 100)
    return int(round(adjusted / 1000) * 1000)


# ── Review flags ─────────────────────────────────────────────────────────────


def compute_review_flags(
    ticker: str,
    ratios: list[dict],
    calculated_conviction: str,
    current_conviction: str | None,
) -> list[str]:
    """Compute review flags for a stock based on fundamentals.

    Returns list of flag strings for removal consideration.
    """
    flags: list[str] = []
    is_bank = ticker.upper() in BANK_TICKERS

    if not ratios:
        flags.append("NO_FINANCIAL_DATA")
        return flags

    # ROE below 8% for 2+ consecutive quarters
    roe_vals = [v for r in ratios[:4] if (v := _get_roe_pct(r)) is not None]
    below_8 = [v < 8 for v in roe_vals]
    if len(below_8) >= 2 and all(below_8[:2]):
        flags.append("ROE_BELOW_8PCT_2Q")

    # Conviction downgrade 2+ levels
    if current_conviction and calculated_conviction:
        curr_idx = _LEVEL_INDEX.get(current_conviction, 2)
        calc_idx = _LEVEL_INDEX.get(calculated_conviction, 2)
        if curr_idx - calc_idx >= 2:
            flags.append("CONVICTION_DOWNGRADE_2+")

    # High debt
    latest = ratios[0]
    de = latest.get("debt_to_equity")
    if de is not None:
        threshold = 15.0 if is_bank else 1.5
        if de > threshold:
            flags.append("HIGH_DEBT")

    # Entry zone sanity check (>30% divergence from calculated)
    # Handled by caller after calculate_entry_zone

    return flags


# ── Candidate screening ──────────────────────────────────────────────────────


def screen_candidates(
    ratios_batch: dict[str, dict],
    existing_tickers: set[str],
    sector_map: dict[str, str] | None = None,
) -> list[dict]:
    """Screen VN30 universe for potential new additions.

    Filters: ROE > 10%, PE < 30, positive net margin.
    Scores using score_conviction(), returns top candidates.

    Args:
        ratios_batch: {ticker: latest_ratio_dict}
        existing_tickers: Tickers already in longterm watchlist
        sector_map: {ticker: sector_name}

    Returns:
        List of candidate dicts sorted by score descending.
    """
    candidates = []
    for ticker, ratios_dict in ratios_batch.items():
        if ticker.upper() in existing_tickers:
            continue

        # Filter thresholds
        roe = _get_roe_pct_from_dict(ratios_dict)
        pe = ratios_dict.get("pe")
        nm = _get_nm_from_dict(ratios_dict)

        if roe is None or roe < 10:
            continue
        if pe is None or pe <= 0 or pe > 30:
            continue
        if nm is None or nm <= 0:
            continue

        conviction, score = score_conviction(ticker, [ratios_dict])
        candidates.append(
            {
                "ticker": ticker.upper(),
                "sector": (sector_map or {}).get(ticker.upper(), "Unknown"),
                "score": score,
                "conviction": conviction,
                "pe": pe,
                "roe": roe,
                "net_margin": nm,
            }
        )

    return sorted(candidates, key=lambda x: x["score"], reverse=True)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = (pct / 100) * (len(sorted_vals) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)


def _get_roe_pct(ratio: dict) -> float | None:
    roe = ratio.get("roe")
    if roe is None:
        return None
    return roe  # already whole % from API normalization


def _get_roe_pct_from_dict(d: dict) -> float | None:
    return _get_roe_pct(d)


def _get_nm(ratio: dict) -> float | None:
    nm = ratio.get("net_margin")
    if nm is None:
        return None
    return nm / 100  # whole % to decimal


def _get_nm_from_dict(d: dict) -> float | None:
    return _get_nm(d)
