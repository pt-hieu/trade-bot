"""Portfolio MCP tools — holdings, trades, cash, watchlist."""

from datetime import date, timedelta

from fastmcp import FastMCP

from shared.neon.portfolio import (
    collapse_holdings_by_ticker,
    get_cash_balance,
    get_portfolio_holdings,
    get_recent_trades,
    get_trades_by_status,
)
from shared.neon.watchlist import get_longterm_watchlist, get_swing_watchlist
from shared.trading_config import get_trading_config


def register(mcp: FastMCP):
    """Register portfolio tools with MCP server."""

    @mcp.tool()
    async def get_portfolio(ticker: str | None = None) -> dict:
        """Get portfolio holdings with P/L, weight, and plan type.

        Prices in VND. Market value in VND.

        Args:
            ticker: Filter to a single ticker (optional).
        """
        holdings = await get_portfolio_holdings()
        # Collapse back to dict[ticker, row] for the MY HOLDINGS contract.
        holdings_by_ticker = {
            ticker_key: dict(slice_row)
            for ticker_key, slice_row in collapse_holdings_by_ticker(holdings).items()
        }
        if ticker:
            ticker = ticker.upper()
            if ticker in holdings_by_ticker:
                return {ticker: holdings_by_ticker[ticker]}
            return {"error": f"{ticker} not found in portfolio"}
        return holdings_by_ticker

    @mcp.tool()
    async def get_trades(
        status: str = "all",
        ticker: str | None = None,
        limit: int = 20,
        days_back: int | None = None,
    ) -> list[dict]:
        """Get trade history from trades_calculated table.

        Args:
            status: OPEN, CLOSED, or all (default: all).
            ticker: Filter by ticker (optional).
            limit: Max trades to return (default: 20).
            days_back: Only trades within N days (optional).
        """
        if status.upper() == "ALL":
            trades = await get_recent_trades(limit=limit)
        else:
            trades = await get_trades_by_status(status=status, limit=limit)

        if ticker:
            ticker = ticker.upper()
            trades = [t for t in trades if t["ticker"] == ticker]

        if days_back:
            cutoff = str(date.today() - timedelta(days=days_back))
            trades = [
                t
                for t in trades
                if t.get("entry_date", "") >= cutoff or t.get("exit_date", "") >= cutoff
            ]

        return trades

    @mcp.tool()
    async def get_cash() -> dict:
        """Get cash balance, minimum reserve, and deployable amount.

        All amounts in VND. Deployable = total - 40M reserve.
        """
        total = await get_cash_balance()
        min_reserve = get_trading_config().min_cash_reserve
        deployable = max(0, total - min_reserve)
        return {
            "total_cash": total,
            "min_reserve": min_reserve,
            "deployable": deployable,
            "can_trade": deployable > 0,
        }

    @mcp.tool()
    async def get_watchlist(watchlist_type: str = "swing") -> dict:
        """Get swing or long-term watchlist.

        Swing: {sector: [tickers]} — grouped by sector.
        Longterm: {ticker: {entry_zone, conviction, sector}} — with entry zones.

        Args:
            watchlist_type: "swing" or "longterm" (default: swing).
        """
        if watchlist_type == "longterm":
            return await get_longterm_watchlist()
        return await get_swing_watchlist()
