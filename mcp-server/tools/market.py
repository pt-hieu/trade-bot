"""Market MCP tools — prices, technicals, market context, catalysts, news."""

from datetime import date

from fastmcp import FastMCP

from shared.api.prices import get_prices as get_prices_vnd
from shared.neon.articles import list_articles_by_ticker, search_articles
from shared.neon.catalyst_summaries import (
    get_active_geopolitical_shock,
    get_catalyst_summary,
)
from shared.neon.market import (
    get_macro_metrics,
    get_market_regime,
    get_sector_rotation,
)
from shared.vnstock_client import fetch_technicals_batch


def register(mcp: FastMCP):
    """Register market tools with MCP server."""

    @mcp.tool()
    async def get_prices(
        tickers: list[str],
        days: int = 10,
    ) -> dict:
        """Get latest OHLCV price data for tickers via vnstock API.

        Prices in VND (converted from vnstock thousands).

        Args:
            tickers: Stock symbols (e.g. ["FPT", "TCB"]).
            days: Lookback days for price history (default: 10).
        """
        return await get_prices_vnd(tickers=tickers, days=days)

    @mcp.tool()
    async def get_technicals(tickers: list[str]) -> dict:
        """Get technical indicators for tickers via vnstock API.

        Returns per ticker: RSI, MACD, SMA20/50, ATR, Supertrend,
        ADX, Bollinger Bands, Stochastic.

        Args:
            tickers: Stock symbols (e.g. ["FPT", "TCB"]).
        """
        return await fetch_technicals_batch(
            symbols=[t.upper() for t in tickers],
        )

    @mcp.tool()
    async def get_market_context(scan_date: str | None = None) -> dict:
        """Get market regime, macro indicators, sector rotation, and geopolitical shock.

        Combines:
        - VN regime: RISK_ON / RISK_OFF / NEUTRAL
        - Global macro: DXY, VIX, USD/VND, global risk regime
        - Sector rotation: hot/cold sectors
        - Geopolitical shock: active crisis phase if any

        Args:
            scan_date: YYYY-MM-DD (default: today).
        """
        d = date.fromisoformat(scan_date) if scan_date else None
        regime = await get_market_regime(d)
        macro = await get_macro_metrics(d)
        rotation = await get_sector_rotation(d)

        try:
            geo_shock = await get_active_geopolitical_shock()
        except Exception:
            geo_shock = None

        return {
            "regime": regime,
            "macro": macro,
            "sector_rotation": rotation,
            "geopolitical_shock": geo_shock,
        }

    @mcp.tool()
    async def get_catalysts() -> dict:
        """Get active catalysts including regulatory events and geopolitical shocks.

        Returns formatted summary of all active catalysts with phase-aware
        display (e.g. "NOW IN IMMEDIATE_SHOCK PHASE") and any active
        geopolitical shock details.
        """
        try:
            summary = await get_catalyst_summary()
        except Exception:
            summary = "Failed to fetch catalysts."

        try:
            geo_shock = await get_active_geopolitical_shock()
        except Exception:
            geo_shock = None

        return {
            "summary": summary,
            "geopolitical_shock": geo_shock,
        }

    @mcp.tool()
    async def get_news(
        query: str | None = None,
        ticker: str | None = None,
    ) -> dict:
        """Search news articles about Vietnamese stocks.

        Either provide a search query OR a ticker symbol.
        Returns article titles, URLs, and snippets from the last 7-14 days.

        Args:
            query: Search keywords (e.g. "banking interest rate", "FDI policy").
            ticker: Stock ticker to find articles about (e.g. "FPT", "TCB").
        """
        scan_date = date.today()

        if ticker:
            articles = await list_articles_by_ticker(ticker.upper(), scan_date, limit=10)
            return {"ticker": ticker.upper(), "articles": articles, "count": len(articles)}
        elif query:
            articles = await search_articles(query, limit=10, scan_date=scan_date)
            return {"query": query, "articles": articles, "count": len(articles)}
        else:
            return {"error": "Provide either query or ticker parameter"}
