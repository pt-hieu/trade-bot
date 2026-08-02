"""Trade queries from trades_calculated."""

from datetime import date
from typing import Any

from ..database import get_db
from ._types import ClosedTradeEntry, OpenedTradeEntry, TradeData, TradesForDateData


async def get_recent_trades(limit: int = 10) -> list[TradeData]:
    """Get recent trades from trades_calculated (source of truth)."""
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT ticker, entry_date, entry_price_vnd, shares, strategy, status,
               exit_date, exit_price_vnd, pl_pct, pl_net_vnd, plan_type
        FROM trades_calculated
        ORDER BY COALESCE(exit_date, entry_date) DESC
        LIMIT $1
    """,
        limit,
    )

    return [_row_to_trade(dict(row)) for row in rows]


async def get_trades_by_status(status: str = "all", limit: int = 50) -> list[TradeData]:
    """Get trades filtered by status (OPEN/CLOSED/PARTIAL/all)."""
    db = await get_db()

    if status.upper() == "ALL":
        rows = await db.fetch_all(
            """
            SELECT ticker, entry_date, entry_price_vnd, shares, strategy, status,
                   exit_date, exit_price_vnd, pl_pct, pl_net_vnd, plan_type
            FROM trades_calculated
            ORDER BY COALESCE(exit_date, entry_date) DESC LIMIT $1
        """,
            limit,
        )
    else:
        rows = await db.fetch_all(
            """
            SELECT ticker, entry_date, entry_price_vnd, shares, strategy, status,
                   exit_date, exit_price_vnd, pl_pct, pl_net_vnd, plan_type
            FROM trades_calculated
            WHERE status = $1
            ORDER BY COALESCE(exit_date, entry_date) DESC LIMIT $2
        """,
            status.upper(),
            limit,
        )

    return [_row_to_trade(dict(row)) for row in rows]


def _row_to_trade(row: dict[str, Any]) -> TradeData:
    """Convert a trades_calculated row to trade dict."""
    return TradeData(
        ticker=row["ticker"],
        entry_date=str(row["entry_date"]) if row["entry_date"] else "",
        entry_price=int(row["entry_price_vnd"]) if row["entry_price_vnd"] else 0,
        shares=row["shares"],
        strategy=row["strategy"],
        status=row["status"],
        exit_date=str(row["exit_date"]) if row["exit_date"] else "",
        exit_price=int(row["exit_price_vnd"]) if row["exit_price_vnd"] else 0,
        pl_pct=float(row["pl_pct"]) if row["pl_pct"] is not None else 0.0,
        plan_type=row["plan_type"] or "SWING",
    )


async def get_trades_for_date(scan_date: date) -> TradesForDateData:
    """Get trades opened or closed on a specific date."""
    db = await get_db()

    opened = await db.fetch_all(
        """
        SELECT ticker, entry_price_vnd, shares, strategy, status
        FROM trades_calculated WHERE entry_date = $1 ORDER BY ticker
    """,
        scan_date,
    )

    closed = await db.fetch_all(
        """
        SELECT ticker, exit_price_vnd, shares, pl_pct, pl_net_vnd
        FROM trades_calculated WHERE exit_date = $1 ORDER BY ticker
    """,
        scan_date,
    )

    return TradesForDateData(
        opened=[
            OpenedTradeEntry(
                ticker=r["ticker"],
                entry_price=int(r["entry_price_vnd"]) if r["entry_price_vnd"] else 0,
                shares=r["shares"],
                strategy=r["strategy"],
                status=r["status"],
            )
            for r in opened
        ],
        closed=[
            ClosedTradeEntry(
                ticker=r["ticker"],
                exit_price=int(r["exit_price_vnd"]) if r["exit_price_vnd"] else 0,
                shares=r["shares"],
                pl_pct=float(r["pl_pct"]) if r["pl_pct"] is not None else 0.0,
                pl_net=int(r["pl_net_vnd"]) if r["pl_net_vnd"] else 0,
            )
            for r in closed
        ],
    )
