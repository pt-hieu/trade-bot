"""Prose formatters — convert portfolio dict data to natural language strings."""

from shared.formatting import format_pct as _format_pct
from shared.formatting import format_price_k as _format_price_k
from shared.formatting import format_vnd as _format_vnd
from shared.neon import TradeData, TradesForDateData
from shared.trading_config import get_trading_config


def _enrich_holding(data: dict) -> dict[str, str | int | float | None]:
    """Create enriched holding dict with display strings added.

    Returns a new dict (does not mutate the TypedDict).
    """
    avg_cost = data.get("avg_cost") or 0
    # Strict pick: never substitute avg_cost for missing current price
    # (Phase 2 §2.2 — same defect class as context_blocks.py:60).
    current = data.get("current_price_vnd")
    weight = data.get("slice_weight_pct") or 0
    pct_change = data.get("pct_from_entry") or 0

    result: dict[str, str | int | float | None] = {
        "ticker": data["ticker"],
        "plan_type": data["plan_type"],
        "shares": data["shares"],
        "avg_cost": data["avg_cost"],
        "avg_cost_vnd": data["avg_cost_vnd"],
        "type": data["type"],
        "current_price_vnd": data["current_price_vnd"],
        "market_value": data["market_value"],
        "slice_weight_pct": data["slice_weight_pct"],
        "ticker_weight_pct": data["ticker_weight_pct"],
        "pct_from_entry": data["pct_from_entry"],
        "breakeven_stop": data["breakeven_stop"],
        "pct_from_entry_str": _format_pct(pct_change),
        "slice_weight_pct_str": f"{weight:.1f}%",
        "ticker_weight_pct_str": f"{data['ticker_weight_pct']:.1f}%",
        "entry_price_str": _format_price_k(avg_cost),
        "current_price_str": _format_price_k(current) if current else "stale",
    }
    return result


def _format_holdings_prose(holdings: list[dict]) -> str:
    """Convert holdings list to natural prose. One line per (ticker, plan_type) slice."""
    if not holdings:
        return "No positions currently held."

    lines = ["Portfolio Holdings:"]
    total_invested = 0.0
    cfg = get_trading_config()

    for slice_row in holdings:
        ticker = slice_row["ticker"]
        shares = slice_row["shares"]
        avg_cost = slice_row["avg_cost"]
        # Strict pick on current and stop precedence (Phase 2 §2.2 sibling of
        # context_blocks.py:60,64). When current is missing, render "stale";
        # when no protective stop is active, render "Stop none active".
        current = slice_row["current_price_vnd"]
        weight = slice_row["slice_weight_pct"]
        pct_change = slice_row["pct_from_entry"] or 0
        plan_type = slice_row["plan_type"]
        active_stop = (
            slice_row.get("catastrophic_floor_vnd")
            or slice_row.get("trailing_stop_vnd")
            or slice_row.get("breakeven_stop")
        )

        if weight > cfg.longterm_review_weight_pct:
            conc = "HIGH concentration"
        elif weight > 20:
            conc = "moderate concentration"
        else:
            conc = ""

        sign = "+" if pct_change >= 0 else ""
        change_str = f"({sign}{pct_change:.1f}%)"

        avg_k = avg_cost / 1000
        curr_k_repr = f"{current / 1000:.1f}k" if current else "stale"
        line = f"{ticker}: {shares} shares at {avg_k:.1f}k entry, now {curr_k_repr} {change_str}."
        if weight > 0:
            line += f" Weight {weight:.1f}%"
            if conc:
                line += f" ({conc})."
            else:
                line += "."
        stop_repr = f"{active_stop / 1000:.1f}k" if active_stop else "none active"
        line += f" Stop at {stop_repr}. {plan_type} position."
        lines.append(line)

        total_invested += weight

    lines.append(f"Total: {len(holdings)} slice(s), {total_invested:.1f}% invested.")
    return "\n".join(lines)


def _format_cash_prose(cash: dict) -> str:
    """Convert cash balance dict to natural prose."""
    if "error" in cash:
        return f"Cash: {cash['error']}"

    total = cash.get("total_cash", 0)
    reserve = cash.get("min_reserve", get_trading_config().min_cash_reserve)
    deployable = cash.get("deployable", 0)
    can_trade = cash.get("can_trade", False)

    status = "Trading allowed." if can_trade else "Insufficient cash for new positions."
    return (
        f"Cash: {_format_vnd(total)} VND total. "
        f"Reserve {_format_vnd(reserve)} (untouchable). "
        f"Deployable {_format_vnd(deployable)} VND for new positions. "
        f"{status}"
    )


def _format_goal_prose(goal: dict) -> str:
    """Convert goal progress dict to natural prose."""
    if "error" in goal:
        return f"Goal: {goal['error']}"

    name = goal.get("name", "Unknown")
    target = goal.get("target", 0)
    realized = goal.get("realized", 0)
    remaining = goal.get("remaining", 0)
    progress = goal.get("progress_pct", 0)
    days_left = goal.get("days_left", 0)
    daily = goal.get("daily_target", 0)
    on_track = goal.get("on_track", False)

    achievability = goal.get("achievability", "")
    achievability_note = goal.get("achievability_note", "")
    if achievability == "UNREACHABLE":
        status = achievability_note or "Goal requires cash contribution to close gap."
    elif achievability == "STRETCH":
        status = achievability_note or "Achievable but requires consistent wins."
    elif on_track:
        status = "On track."
    else:
        status = "Behind schedule."

    return (
        f"Goal: {name}. Target {_format_vnd(target)}, "
        f"realized {_format_vnd(realized)} ({progress:.1f}%). "
        f"Remaining {_format_vnd(remaining)} in {days_left} days "
        f"(need {_format_vnd(daily)}/day). {status}"
    )


def _format_trades_prose(trades: list[TradeData]) -> str:
    """Convert trades list to natural prose."""
    if not trades:
        return "No recent trades."

    lines = [f"Recent Trades ({len(trades)}):"]
    for t in trades:
        ticker = t.get("ticker", "?")
        entry_date = t.get("entry_date", "?")
        entry_price = t.get("entry_price", 0)
        status = t.get("status", "OPEN")
        strategy = t.get("strategy", "?")

        if status == "CLOSED":
            exit_price = t.get("exit_price", 0)
            pl_pct = t.get("pl_pct", 0)
            sign = "+" if pl_pct >= 0 else ""
            result = "WIN" if pl_pct > 0 else "LOSS"
            lines.append(
                f"{ticker}: {strategy} trade, entered {entry_date} at {entry_price / 1000:.1f}k, "
                f"exited at {exit_price / 1000:.1f}k ({sign}{pl_pct:.1f}% {result})."
            )
        else:
            lines.append(
                f"{ticker}: {strategy} trade, entered {entry_date} at {entry_price / 1000:.1f}k. "
                f"Status: {status}."
            )

    return "\n".join(lines)


def _format_trades_for_date_prose(trades: TradesForDateData) -> str:
    """Convert trades-for-date dict to natural prose."""
    opened = trades["opened"]
    closed = trades["closed"]

    if not opened and not closed:
        return "No trades recorded for this date."

    lines = []
    if opened:
        lines.append(f"Opened {len(opened)} position(s):")
        for t in opened:
            ticker = t.get("ticker", "?")
            price = t.get("entry_price", 0) / 1000
            shares = t.get("shares", 0)
            lines.append(f"  {ticker}: {shares} shares at {price:.1f}k")

    if closed:
        lines.append(f"Closed {len(closed)} position(s):")
        for t in closed:
            ticker = t.get("ticker", "?")
            price = t.get("exit_price", 0) / 1000
            pl_pct = t.get("pl_pct", 0)
            sign = "+" if pl_pct >= 0 else ""
            lines.append(f"  {ticker}: exited at {price:.1f}k ({sign}{pl_pct:.1f}%)")

    return "\n".join(lines)


def _format_watchlist_prose(watchlist: dict) -> str:
    """Convert longterm watchlist dict to natural prose."""
    if "error" in watchlist:
        return f"Watchlist: {watchlist['error']}"

    if not watchlist:
        return "No stocks in watchlist."

    high = []
    medium = []
    other = []

    for ticker, data in watchlist.items():
        conviction = data.get("conviction", "").lower()
        entry_vnd = data.get("entry_zone", 0)
        sector = data.get("sector", "?")
        entry_str = f"{entry_vnd / 1000:.1f}" if entry_vnd else "?"

        info = f"{ticker} ({sector}): entry zone {entry_str}k"

        if conviction in ["high"]:
            high.append(info)
        elif conviction in ["medium-high", "medium"]:
            medium.append(info)
        else:
            other.append(info)

    lines = [f"Long-Term Watchlist ({len(watchlist)} stocks):"]
    if high:
        lines.append(f"HIGH conviction: {'; '.join(high)}")
    if medium:
        lines.append(f"MEDIUM conviction: {'; '.join(medium)}")
    if other:
        lines.append(f"Other: {'; '.join(other)}")

    return "\n".join(lines)
