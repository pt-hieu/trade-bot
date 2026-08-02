#!/usr/bin/env python3
"""
Deterministic pattern extraction from trading evaluation data.

All calculations are pure Python — no LLM agent needed.
Replaces the former PydanticAI pattern agent (deactivated in migration 049).
"""

from collections import defaultdict

from .rules import compute_actionable_rules, persist_actionable_rules  # noqa: F401

# Minimum sample size for a pattern to be included.
# Single trades don't constitute a pattern — require at least 5 samples.
_MIN_SAMPLE_SIZE = 5
# Strategy is coarser-grained — useful at smaller sample sizes.
_MIN_STRATEGY_SAMPLE_SIZE = 3
# Lower threshold for losing patterns — losses spread across action types
# rarely accumulate 5 samples per type, so use 3 to surface them.
_MIN_LOSING_SAMPLE_SIZE = 3

# Action descriptions for templated pattern strings
_ACTION_LABELS: dict[str, str] = {
    "BUY": "BUY entry signals",
    "ADD": "ADD position signals",
    "HOLD": "HOLD recommendations",
    "EXIT": "EXIT signals",
    "TRIM": "TRIM partial-profit signals",
    "AVOID": "AVOID/skip signals",
    "SKIP": "SKIP signals",
    "WAIT": "WAIT signals",
    "WATCH": "WATCH-only signals",
}

# Error types produced by the LLM evaluator
_ERROR_TYPES = ("ANALYSIS_ERROR", "EXECUTION_ERROR", "CALIBRATION_ERROR", "VARIANCE")


def calc_action_stats(daily_records: list[dict], rolling_days: int) -> dict:
    """Calculate win rates per action type from evaluation data."""
    stats = defaultdict(lambda: {"total": 0, "won": 0})
    for record in daily_records[-rolling_days:]:
        for e in record.get("evaluations", []):
            if e.get("won") is None:  # skip EXCLUDED (WAIT/WATCH/AVOID/SKIP)
                continue
            action = e.get("recommendation", "UNKNOWN")
            stats[action]["total"] += 1
            if e.get("won"):
                stats[action]["won"] += 1
    return dict(stats)


def _calc_action_error_breakdown(
    daily_records: list[dict],
    rolling_days: int,
) -> dict[str, dict]:
    """Calculate error type counts for losing evaluations per action type.

    Only counts non-wins (losses) that have an error_type set by the LLM evaluator.
    Returns dict: action → {ANALYSIS_ERROR: N, EXECUTION_ERROR: N, VARIANCE: N}
    """
    breakdown: dict[str, dict] = defaultdict(
        lambda: {"ANALYSIS_ERROR": 0, "EXECUTION_ERROR": 0, "CALIBRATION_ERROR": 0, "VARIANCE": 0}
    )
    for record in daily_records[-rolling_days:]:
        for e in record.get("evaluations", []):
            if e.get("won") is None or e.get("won"):
                continue  # skip EXCLUDED and wins — only classify losses
            action = e.get("recommendation", "UNKNOWN")
            error_type = e.get("error_type", "")
            if error_type in _ERROR_TYPES:
                breakdown[action][error_type] += 1
    return dict(breakdown)


def _calc_strategy_stats(
    daily_records: list[dict],
    rolling_days: int,
) -> dict[str, dict]:
    """Calculate win rates per strategy type from evaluation data."""
    stats: dict[str, dict] = defaultdict(lambda: {"total": 0, "won": 0})
    for record in daily_records[-rolling_days:]:
        for e in record.get("evaluations", []):
            if e.get("won") is None:  # skip EXCLUDED
                continue
            strategy = e.get("strategy")
            if not strategy or strategy == "UNCLASSIFIED":
                continue
            stats[strategy]["total"] += 1
            if e.get("won"):
                stats[strategy]["won"] += 1
    return dict(stats)


def _calc_ticker_stats(
    daily_records: list[dict],
    rolling_days: int,
) -> dict[str, dict]:
    """Calculate win rates per ticker from evaluation data."""
    stats: dict[str, dict] = defaultdict(lambda: {"total": 0, "won": 0})
    for record in daily_records[-rolling_days:]:
        for e in record.get("evaluations", []):
            if e.get("won") is None:  # skip EXCLUDED
                continue
            ticker = e.get("ticker")
            if ticker:
                stats[ticker]["total"] += 1
                if e.get("won"):
                    stats[ticker]["won"] += 1
    return dict(stats)


def _calc_sector_stats(
    ticker_stats: dict[str, dict],
    sector_map: dict[str, str],
) -> dict[str, dict]:
    """Aggregate ticker stats into sector stats."""
    stats: dict[str, dict] = defaultdict(lambda: {"total": 0, "won": 0})
    for ticker, s in ticker_stats.items():
        sector = sector_map.get(ticker)
        if sector:
            stats[sector]["total"] += s["total"]
            stats[sector]["won"] += s["won"]
    return dict(stats)


def _classify_sector_bias(win_rate: float) -> str:
    """Derive sector bias deterministically from win rate."""
    if win_rate >= 0.6:
        return "bullish"
    if win_rate <= 0.4:
        return "bearish"
    return "neutral"


def _dominant_error(error_bd: dict) -> str:
    """Return the dominant error type from a breakdown dict."""
    if not any(error_bd.values()):
        return "N/A"
    return max(error_bd, key=lambda k: error_bd[k])


def _build_action_patterns(
    action_stats: dict,
    sector_map: dict[str, str] | None,
    ticker_stats: dict[str, dict],
    action_error_breakdown: dict[str, dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Build winning/losing pattern dicts from per-action stats."""
    # Find top sector for actionable rule context
    top_sector = ""
    if sector_map:
        sector_stats = _calc_sector_stats(ticker_stats, sector_map)
        best = max(
            sector_stats.items(),
            key=lambda x: x[1]["won"] / x[1]["total"] if x[1]["total"] else 0,
            default=None,
        )
        if best:
            top_sector = best[0]

    winning, losing = [], []
    for action, s in sorted(action_stats.items()):
        rate = round(s["won"] / s["total"], 2) if s["total"] > 0 else 0.0
        min_required = _MIN_LOSING_SAMPLE_SIZE if rate < 0.5 else _MIN_SAMPLE_SIZE
        if s["total"] < min_required:
            continue
        loss_rate = round(1.0 - rate, 2)
        label = _ACTION_LABELS.get(action, f"{action} signals")
        pct = round(rate * 100)

        pattern = {
            "pattern": f"{label}: {s['won']}/{s['total']} correct ({pct}%)",
            "action": action,
            "win_rate": rate,
            "loss_rate": loss_rate,
            "sample_size": s["total"],
        }

        if rate >= 0.5:
            sector_hint = f" — prioritize in {top_sector}" if top_sector else ""
            pattern["actionable_rule"] = (
                f"{action} signals at {pct}% win rate over {s['total']} trades{sector_hint}"
            )
            pattern["avoid_rule"] = ""
            winning.append(pattern)
        else:
            # Add error breakdown for losing patterns
            error_bd = (action_error_breakdown or {}).get(
                action, {"ANALYSIS_ERROR": 0, "EXECUTION_ERROR": 0, "VARIANCE": 0}
            )
            dom_error = _dominant_error(error_bd)
            pattern["error_breakdown"] = dict(error_bd)
            pattern["dominant_error"] = dom_error

            pattern["actionable_rule"] = ""
            pattern["avoid_rule"] = (
                f"{action} signals failing at {round(loss_rate * 100)}% — reduce size or skip"
            )
            losing.append(pattern)

    return winning, losing


async def extract_patterns(
    daily_records: list[dict] | None = None,
    rolling_days: int = 7,
    sector_map: dict[str, str] | None = None,
    scan_date=None,
) -> dict:
    """Extract patterns deterministically from rolling evaluation history.

    Args:
        daily_records: List of daily evaluation records
        rolling_days: Number of days to analyze
        sector_map: Ticker → sector name mapping

    Returns:
        Dict with winning_patterns, losing_patterns, sector_insights, ticker_insights
    """
    records = daily_records or []
    if not records:
        return _empty_result()

    action_stats = calc_action_stats(records, rolling_days)
    ticker_stats = _calc_ticker_stats(records, rolling_days)
    action_error_breakdown = _calc_action_error_breakdown(records, rolling_days)
    strategy_stats = _calc_strategy_stats(records, rolling_days)

    # Action-level patterns
    winning, losing = _build_action_patterns(
        action_stats,
        sector_map,
        ticker_stats,
        action_error_breakdown,
    )

    # Ticker insights
    tickers = []
    for ticker, s in sorted(ticker_stats.items()):
        if s["total"] < _MIN_SAMPLE_SIZE:
            continue
        tickers.append(
            {
                "ticker": ticker,
                "recent_accuracy": round(s["won"] / s["total"], 2),
            }
        )

    # Sector insights
    sectors = []
    if sector_map:
        sector_stats = _calc_sector_stats(ticker_stats, sector_map)
        for sector, s in sorted(sector_stats.items()):
            if s["total"] < _MIN_SAMPLE_SIZE:
                continue
            rate = round(s["won"] / s["total"], 2)
            sectors.append(
                {
                    "sector": sector,
                    "bias": _classify_sector_bias(rate),
                    "win_rate": rate,
                }
            )

    # Strategy insights (per-strategy win rate)
    strategy_insights = []
    for strategy, s in sorted(strategy_stats.items()):
        if s["total"] < _MIN_STRATEGY_SAMPLE_SIZE:
            continue
        rate = round(s["won"] / s["total"], 2)
        strategy_insights.append(
            {
                "strategy": strategy,
                "win_rate": rate,
                "sample_size": s["total"],
            }
        )

    actionable_rules = compute_actionable_rules(losing)

    # Quantitative calibration stats (aggregated from calibration fields on entry evals)
    from .calibration import calc_calibration_stats

    calibration = calc_calibration_stats(records, rolling_days, scan_date=scan_date)

    print(
        f"    Extracted {len(winning)} winning, {len(losing)} losing patterns, "
        f"{len(actionable_rules)} actionable rules, {len(strategy_insights)} strategy insights"
    )
    return {
        "winning_patterns": winning,
        "losing_patterns": losing,
        "sector_insights": sectors,
        "ticker_insights": tickers,
        "actionable_rules": actionable_rules,
        "strategy_insights": strategy_insights,
        "calibration_insights": calibration,
    }


def _empty_result() -> dict:
    return {
        "winning_patterns": [],
        "losing_patterns": [],
        "sector_insights": [],
        "ticker_insights": [],
        "actionable_rules": [],
        "strategy_insights": [],
        "calibration_insights": {},
    }
