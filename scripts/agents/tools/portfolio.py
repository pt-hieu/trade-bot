"""Portfolio tools for PydanticAI agents — async data functions."""

from datetime import date

from shared.neon import (
    get_active_goal as _get_active_goal_async,
)
from shared.neon import (
    get_active_goals as _get_active_goals_async,
)
from shared.neon import (
    get_cash_balance as _get_cash_balance_async,
)
from shared.neon import (
    get_learnings_summary as _get_learnings_summary_async,
)
from shared.neon import (
    get_longterm_watchlist as _get_longterm_watchlist_async,
)
from shared.neon import (
    get_portfolio_holdings as _get_portfolio_holdings_async,
)
from shared.neon import (
    get_recent_trades as _get_recent_trades_async,
)
from shared.neon import (
    get_swing_trade_stats as _get_swing_trade_stats_async,
)
from shared.neon import (
    get_trades_for_date as _get_trades_for_date_async,
)
from shared.rules.constraints import compute_goal_metrics as _compute_goal_metrics
from shared.rules.geopolitical import SHOCK_MULTIPLIER_MAP
from shared.trading_config import get_trading_config

from .portfolio_formatters import (
    _enrich_holding,
    _format_cash_prose,
    _format_holdings_prose,
    _format_trades_for_date_prose,
    _format_trades_prose,
    _format_watchlist_prose,
)

# Re-exports for external import sites
from .portfolio_learnings import get_learnings_async  # noqa: F401
from .trailing_stops import compute_trailing_stop  # noqa: F401


async def get_holdings_async() -> dict:
    """Get current portfolio holdings from database (async).

    Returns:
        Dict with holdings list (enriched with display strings) and prose summary.
    """
    try:
        holdings = await _get_portfolio_holdings_async()
        if not holdings:
            return {"error": "No holdings found", "prose": "No holdings found."}
        enriched = [_enrich_holding(slice_row) for slice_row in holdings]
        return {"holdings": enriched, "prose": _format_holdings_prose(holdings)}
    except Exception as e:
        return {
            "error": f"Failed to fetch holdings: {e}",
            "prose": f"Failed to fetch holdings: {e}",
        }


async def get_cash_balance_async() -> dict:
    """Get current cash balance from database (async).

    Returns:
        Dict with total_cash, min_reserve, deployable, and prose summary.
    """
    cfg = get_trading_config()
    min_reserve = cfg.min_cash_reserve

    try:
        total_cash = await _get_cash_balance_async()
        deployable = max(0, total_cash - min_reserve)
        result = {
            "total_cash": total_cash,
            "min_reserve": min_reserve,
            "deployable": deployable,
            "can_trade": deployable > cfg.low_cash_threshold,
        }
        result["prose"] = _format_cash_prose(result)
        return result
    except Exception as e:
        return {
            "error": f"Failed to fetch cash balance: {e}",
            "prose": f"Cash: Failed to fetch - {e}",
        }


async def get_longterm_watchlist_async(
    filter_type: str = "all",
    sector: str | None = None,
) -> dict:
    """Get long-term investment watchlist from database (async).

    Args:
        filter_type: "all", "high_conviction", or "by_sector"
        sector: Filter by sector name (required if filter_type="by_sector")

    Returns:
        Dict with watchlist data and prose summary.
    """
    try:
        watchlist = await _get_longterm_watchlist_async()
        if not watchlist:
            return {"error": "No watchlist found", "prose": "No stocks in long-term watchlist."}

        if filter_type == "high_conviction":
            watchlist = {
                k: v
                for k, v in watchlist.items()
                if v.get("conviction", "").lower() in ["high", "medium-high"]
            }
        elif filter_type == "by_sector" and sector:
            watchlist = {
                k: v for k, v in watchlist.items() if sector.lower() in v.get("sector", "").lower()
            }

        return {"watchlist": watchlist, "prose": _format_watchlist_prose(watchlist)}
    except Exception as e:
        return {
            "error": f"Failed to fetch watchlist: {e}",
            "prose": f"Watchlist: Failed to fetch - {e}",
        }


async def get_recent_trades_async(limit: int = 10) -> dict:
    """Get recent trades from database (async).

    Args:
        limit: Maximum number of trades to return

    Returns:
        Dict with trades list and prose summary.
    """
    try:
        trades = await _get_recent_trades_async(limit)
        trades = trades if trades else []
        return {"trades": trades, "prose": _format_trades_prose(trades)}
    except Exception as e:
        return {
            "error": f"Failed to fetch trades: {e}",
            "trades": [],
            "prose": f"Trades: Failed to fetch - {e}",
        }


async def get_trades_for_date_async(scan_date: date) -> dict:
    """Get trades executed on a specific date (async).

    Args:
        scan_date: The date to check for trades

    Returns:
        Dict with opened/closed lists and prose summary.
    """
    try:
        result = await _get_trades_for_date_async(scan_date)
        return {**result, "prose": _format_trades_for_date_prose(result)}
    except Exception as e:
        return {
            "error": f"Failed to fetch trades: {e}",
            "opened": [],
            "closed": [],
            "prose": f"Trades: Failed to fetch - {e}",
        }


async def get_goal_progress_async(scan_date: "date | None" = None) -> dict:
    """Get active trading goal progress with pre-computed urgency tier (async)."""
    try:
        goal = await _get_active_goal_async()
        if not goal:
            return {"error": "No active goal", "prose": "No active trading goal."}

        cash = await get_cash_balance_async()
        deployable = cash.get("deployable", 0)
        trade_stats = await _get_swing_trade_stats_async()
        return _compute_goal_metrics(goal, deployable, trade_stats, scan_date=scan_date)
    except Exception as e:
        return {"error": f"Failed to fetch goal: {e}", "prose": f"Goal: Failed to fetch - {e}"}


async def get_all_goals_progress_async(
    cash: dict | None = None, scan_date: "date | None" = None
) -> list[dict]:
    """Get progress for ALL active goals (async).

    Args:
        cash: Pre-fetched cash balance dict. If None, fetches internally.
        scan_date: Pipeline scan date for days_left calculation.
    """
    try:
        goals = await _get_active_goals_async()
        if not goals:
            return []

        if cash is None:
            cash = await get_cash_balance_async()
        deployable = cash.get("deployable", 0)
        trade_stats = await _get_swing_trade_stats_async()
        return [
            _compute_goal_metrics(goal, deployable, trade_stats, scan_date=scan_date)
            for goal in goals
        ]
    except Exception as e:
        return [{"error": f"Failed to fetch goals: {e}", "prose": f"Goals: Failed to fetch - {e}"}]


async def get_position_scale_factor() -> dict:
    """Calculate position size multiplier based on recent win rate.

    Returns:
        Dict with scale_factor (0.25-1.0), win_rate, note, and prose.
    """
    try:
        summary = await _get_learnings_summary_async()
        overall_win_rate = (summary.get("overall_win_rate") or 50) if summary else 50

        # Use swing-specific win rate with minimum sample blending
        swing_win_rate = summary.get("swing_win_rate") if summary else None
        swing_sample_size = summary.get("swing_sample_size") if summary else None

        if swing_sample_size is not None and swing_sample_size >= 10 and swing_win_rate is not None:
            win_rate = swing_win_rate
        elif swing_sample_size is not None and swing_sample_size > 0 and swing_win_rate is not None:
            blend = swing_sample_size / 10
            win_rate = blend * swing_win_rate + (1 - blend) * overall_win_rate
        else:
            win_rate = overall_win_rate

        cfg = get_trading_config()

        if win_rate >= cfg.full_winrate_threshold:
            scale = 1.0
            note = "Normal sizing"
        elif win_rate >= cfg.reduced_winrate_threshold:
            scale = 0.85
            note = "Reduced sizing (moderate win rate)"
        elif win_rate >= cfg.half_winrate_threshold:
            scale = 0.7
            note = "Reduced sizing (low win rate)"
        else:
            scale = max(cfg.minimal_scale_factor, 0.5)
            note = "Half sizing (very low win rate — floor at 50% to keep trades meaningful)"

        # Geopolitical shock multiplier (deterministic, date-based)
        from shared.neon.catalyst_summaries import get_active_geopolitical_shock

        geo_shock = await get_active_geopolitical_shock()
        shock_multiplier = 1.0
        if geo_shock:
            phase_name = geo_shock.get("phase_name") or ""
            shock_multiplier = SHOCK_MULTIPLIER_MAP.get(phase_name, 1.0)
            if shock_multiplier != 1.0:
                note += f" | SHOCK: {shock_multiplier}x (geo phase: {phase_name})"

        final_scale = round(scale * shock_multiplier, 2)

        win_rate_source = (
            "swing"
            if swing_sample_size is not None and swing_sample_size >= 10
            else (
                f"blended (swing n={swing_sample_size})"
                if swing_sample_size is not None and swing_sample_size > 0
                else "overall"
            )
        )
        return {
            "scale_factor": final_scale,
            "win_rate": win_rate,
            "swing_win_rate": swing_win_rate,
            "swing_sample_size": swing_sample_size,
            "shock_multiplier": shock_multiplier,
            "note": note,
            "prose": f"Position scale: {final_scale}x ({note}). Win rate: {win_rate:.1f}% ({win_rate_source})",
        }
    except Exception as e:
        return {
            "scale_factor": 0.75,
            "win_rate": 0,
            "shock_multiplier": 1.0,
            "note": "Defaulting to 75% size (error fetching win rate — unknown != bad)",
            "prose": f"Position scale: 0.75x (error: {e})",
        }


async def get_sector_allocation_async() -> dict:
    """Get sector allocation targets vs actual with drift analysis."""
    import logging

    logger = logging.getLogger(__name__)
    try:
        from shared.neon import get_portfolio_holdings, get_sector_allocations

        allocations = await get_sector_allocations()
        holdings = await get_portfolio_holdings()

        if not allocations:
            return {
                "error": "No sector allocations configured",
                "prose": "No sector allocation targets configured.",
            }

        total_value = sum(
            (slice_row.get("market_value_vnd") or slice_row.get("market_value") or 0)
            for slice_row in (holdings or [])
        )

        sector_values: dict[str, float] = {}
        for slice_row in holdings or []:
            sector = (slice_row.get("sector") or "unknown").lower()
            value = slice_row.get("market_value_vnd") or slice_row.get("market_value") or 0
            sector_values[sector] = sector_values.get(sector, 0) + value

        parts = ["Sector Allocation (Target vs Actual):"]
        for alloc in allocations:
            sector_name = (alloc.get("sector_name") or "?").lower()
            target_pct = float(alloc.get("target_pct") or 0)
            actual_value = sector_values.get(sector_name, 0)
            actual_pct = (actual_value / total_value * 100) if total_value > 0 else 0
            drift = actual_pct - target_pct

            if drift > 5:
                status = "OVERWEIGHT"
            elif drift < -5:
                status = "UNDERWEIGHT"
            else:
                status = "ON TARGET"

            parts.append(
                f"  {sector_name.title()}: target {target_pct:.0f}%, actual {actual_pct:.0f}%"
                f" ({status}, drift {drift:+.0f}%)"
            )

        return {"allocations": allocations, "prose": "\n".join(parts)}
    except Exception as e:
        logger.warning("get_sector_allocation_async failed: %s", e)
        return {"error": str(e), "prose": f"Sector allocation unavailable: {e}"}


def _format_ensemble_history_prose(ticker: str, votes: list[dict], days_back: int) -> dict:
    """Format a single ticker's ensemble votes as prose + structured dict."""
    from collections import Counter

    if not votes:
        return {
            "error": f"No ensemble history for {ticker}",
            "prose": f"{ticker}: No ensemble vote history in last {days_back}d.",
        }

    by_date: dict[str, list] = {}
    for vote in votes:
        vote_date = str(vote.get("record_date") or "?")
        by_date.setdefault(vote_date, []).append(vote)

    parts = [f"{ticker} Ensemble Vote History ({days_back}d, {len(by_date)} sessions):"]
    for vote_date, day_votes in sorted(by_date.items(), reverse=True)[:5]:
        vote_strs = []
        for vote in day_votes:
            analyst = vote.get("analyst_type") or "?"
            action = vote.get("action") or "?"
            confidence = vote.get("confidence") or 0
            vote_strs.append(f"{analyst}={action}({confidence})")
        parts.append(f"  [{vote_date}] {', '.join(vote_strs)}")

    actions = [vote.get("action") or "HOLD" for vote in votes]
    action_counts = Counter(actions)
    dominant = action_counts.most_common(1)[0]
    parts.append(f"  Dominant action: {dominant[0]} ({dominant[1]}/{len(actions)} votes)")

    exit_count = action_counts.get("EXIT", 0)
    if exit_count >= 3:
        parts.append(f"  EXIT signaled {exit_count}x in {days_back}d — check if being ignored")

    return {"votes": votes, "prose": "\n".join(parts)}


async def get_ensemble_history_async(ticker: str, days_back: int = 7) -> dict:
    """Get historical ensemble analyst votes for a single position (delegates to batch)."""
    import logging

    logger = logging.getLogger(__name__)
    try:
        from shared.neon import get_ensemble_vote_history_batch

        batch = await get_ensemble_vote_history_batch([ticker], days_back)
        return _format_ensemble_history_prose(
            ticker.upper(), batch.get(ticker.upper(), []), days_back
        )
    except Exception as e:
        logger.warning("get_ensemble_history_async failed for %s: %s", ticker, e)
        return {"error": str(e), "prose": f"{ticker}: Ensemble history unavailable - {e}"}


async def get_ensemble_history_batch_async(
    tickers: list[str], days_back: int = 7
) -> dict[str, dict]:
    """Get historical ensemble analyst votes for a batch of positions in one query."""
    import logging

    logger = logging.getLogger(__name__)
    try:
        from shared.neon import get_ensemble_vote_history_batch

        batch = await get_ensemble_vote_history_batch(tickers, days_back)
        return {
            ticker.upper(): _format_ensemble_history_prose(
                ticker.upper(), batch.get(ticker.upper(), []), days_back
            )
            for ticker in tickers
        }
    except Exception as e:
        logger.warning("get_ensemble_history_batch_async failed: %s", e)
        return {
            ticker.upper(): {
                "error": str(e),
                "prose": f"{ticker.upper()}: Ensemble history unavailable - {e}",
            }
            for ticker in tickers
        }
