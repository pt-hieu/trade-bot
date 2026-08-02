"""Company domain tools."""

import logging

from ...types import RequiredTickers
from ..registry import ToolDomain, register_domain_tool

logger = logging.getLogger(__name__)


def _format_profile_prose(ticker: str, profile: dict) -> str:
    """Format a profile dict into prose for LLM consumption."""
    parts = [f"=== {ticker} Company Profile ==="]
    if summary := profile.get("business_summary") or "":
        parts.append(f"Business: {summary}")
    if segments := profile.get("revenue_segments") or []:
        seg_strs = [f"{s.get('name') or '?'} ({s.get('pct_revenue') or '?'}%)" for s in segments]
        parts.append(f"Revenue: {', '.join(seg_strs)}")
    if export := profile.get("export_split") or {}:
        dom = export.get("domestic_pct") or "?"
        exports = export.get("exports") or []
        exp_strs = [f"{e.get('market') or '?'} {e.get('pct_revenue') or '?'}%" for e in exports]
        market_str = f"{dom}% domestic"
        if exp_strs:
            market_str += f" | {', '.join(exp_strs)}"
        parts.append(f"Markets: {market_str}")
    if chain := profile.get("supply_chain") or []:
        chain_strs = [
            f"{c.get('input') or '?'} ({c.get('pct_cost') or '?'}% cost, "
            f"from {', '.join(c.get('source_countries') or ['?'])})"
            for c in chain
        ]
        parts.append(f"Supply chain: {', '.join(chain_strs)}")
    if macro := profile.get("macro_sensitivities") or []:
        parts.append("Macro Sensitivities:")
        for sensitivity in macro:
            factor = sensitivity.get("factor") or "?"
            direction = sensitivity.get("direction") or "?"
            magnitude = sensitivity.get("magnitude") or "?"
            explanation = sensitivity.get("explanation") or ""
            parts.append(f"  {factor}: {direction} ({magnitude}) — {explanation}")
    if comp := profile.get("competitive_position") or {}:
        moat = comp.get("moat") or "?"
        share = comp.get("market_share") or "?"
        power = comp.get("pricing_power") or "?"
        parts.append(f"Competitive: Moat={moat}, Share={share}, Pricing={power}")
    return "\n".join(parts)


async def get_profile(tickers: RequiredTickers) -> str:
    """Get company profiles: business model, sector, supply chain, macro sensitivities.
    Pass a list like ['FPT', 'TCB']. Fetches all in one DB query.

    Returns:
        Prose block per ticker starting with "=== {TICKER} Company Profile ==="
        and including Business, Revenue segments, Markets (export split),
        Supply chain, Macro Sensitivities, and Competitive position
        lines. Missing-profile entries say "No company profile available.
        Request research to enable macro sensitivity analysis."
    """
    from shared.neon.company_profiles import get_profiles_batch

    try:
        profiles = await get_profiles_batch([t.upper() for t in tickers])
    except Exception as error:
        logger.warning("get_profiles_batch failed: %s", error)
        profiles = []

    profile_map = {p["ticker"]: p for p in profiles}
    parts: list[str] = []
    for ticker in tickers:
        upper = ticker.upper()
        if upper in profile_map:
            parts.append(_format_profile_prose(upper, profile_map[upper]))
        else:
            parts.append(
                f"{upper}: No company profile available. "
                "Request research to enable macro sensitivity analysis."
            )
    return "\n\n".join(parts)


async def get_macro_affected(macro_factor: str) -> str:
    """Get tickers affected by a macro factor (e.g. 'interest_rate', 'usd_vnd').

    Returns:
        Prose "Tickers affected by {factor}:" + indented lines with
        direction/magnitude/explanation. "Error: no factor provided",
        "No tickers with known sensitivity to '{factor}'.", or
        "Macro factor lookup unavailable..." on edge cases.
    """
    from ...company_profiles import tool_get_macro_affected_tickers

    return await tool_get_macro_affected_tickers(macro_factor)


register_domain_tool(
    "company.get_profile",
    ToolDomain.COMPANY,
    get_profile,
    accepts_tickers=True,
    returns_hint="prose per ticker — business + macro sensitivities",
)
register_domain_tool(
    "company.get_macro_affected",
    ToolDomain.COMPANY,
    get_macro_affected,
    returns_hint="prose — indented list of affected tickers",
)
