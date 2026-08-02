"""Knowledge base MCP tools — company profiles and macro sensitivity."""

from fastmcp import FastMCP

from shared.macro_factors import MACRO_FACTORS
from shared.neon.company_profiles import (
    get_company_profile,
    resolve_tickers_by_macro_factor,
)

_VALID_FACTORS = sorted(MACRO_FACTORS.keys())


def register(mcp: FastMCP):
    """Register knowledge base tools with MCP server."""

    @mcp.tool()
    async def get_company_knowledge(ticker: str) -> dict:
        """Get company business model, revenue segments, supply chain, and macro sensitivities.

        Args:
            ticker: Stock ticker (e.g. FPT, TCB, HPG).
        """
        profile = await get_company_profile(ticker.upper())
        if not profile:
            return {"error": f"No profile for {ticker}. Populate via company research."}
        return profile

    @mcp.tool()
    async def get_macro_affected(factor: str) -> list[dict] | dict:
        """Find tickers affected by a macro factor, with direction and magnitude.

        Args:
            factor: Macro factor key. Options: ai_disruption, banking_regulation,
                    china_demand, copper, credit_growth, dxy, fdi, global_risk,
                    interest_rate, iron_ore, japan_demand, land_law, npl_rules,
                    oil_price, public_investment, rubber, securities_regulation,
                    steel_price, us_demand, usd_vnd, vix.
        """
        if factor not in MACRO_FACTORS:
            return {"error": f"Unknown factor '{factor}'", "valid_factors": _VALID_FACTORS}
        return await resolve_tickers_by_macro_factor(factor)
