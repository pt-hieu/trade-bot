"""Fundamentals MCP tools — financial statements and ratios."""

from fastmcp import FastMCP

from shared.api.fundamentals import (
    get_financial_ratios,
    get_financial_ratios_batch,
    get_financial_statements,
)


def register(mcp: FastMCP):
    """Register fundamentals tools with MCP server."""

    @mcp.tool()
    async def get_financials(
        ticker: str,
        report_type: str = "ratios",
        periods: int = 4,
    ) -> dict:
        """Get financial data for a stock.

        Returns historical financial ratios, income statements,
        balance sheets, or cash flow data.

        Args:
            ticker: Stock symbol (e.g., "FPT").
            report_type: ratios (default), income, balance_sheet, or cash_flow.
            periods: Number of periods to return (default: 4).
        """
        ticker = ticker.upper()

        if report_type == "ratios":
            data = await get_financial_ratios(ticker, periods)
            return {"ticker": ticker, "type": "ratios", "data": data, "count": len(data)}

        if report_type in ("income", "balance_sheet", "cash_flow"):
            data = await get_financial_statements(ticker, report_type, periods)
            return {"ticker": ticker, "type": report_type, "data": data, "count": len(data)}

        return {
            "error": f"Invalid report_type: {report_type}. Use: ratios, income, balance_sheet, cash_flow"
        }

    @mcp.tool()
    async def compare_financials(tickers: list[str]) -> dict:
        """Compare financial ratios across multiple stocks.

        Returns latest PE, PB, ROE, margins, debt/equity for each ticker.

        Args:
            tickers: Stock symbols (e.g., ["FPT", "TCB", "VHM"]).
        """
        data = await get_financial_ratios_batch([t.upper() for t in tickers])
        return {"comparison": data, "count": len(data)}
