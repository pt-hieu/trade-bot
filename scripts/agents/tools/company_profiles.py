"""Company profile agent tools — prose format for LLM agents via registry."""

import logging

logger = logging.getLogger(__name__)


async def tool_get_company_profile(ticker: str) -> str:
    """Get company business model, supply chain, and macro sensitivities.

    Args:
        ticker: Stock ticker (e.g., 'HPG', 'FPT')
    """
    if not ticker:
        return "Error: no ticker provided"

    from shared.neon import get_company_profile

    try:
        profile = await get_company_profile(ticker.upper())
    except Exception as error:
        logger.warning("tool_get_company_profile failed for %s: %s", ticker, error)
        return f"{ticker.upper()}: Company profile unavailable: {error}"
    if not profile:
        return (
            f"{ticker.upper()}: No company profile available. "
            "Request research to enable macro sensitivity analysis."
        )

    parts = [f"=== {ticker.upper()} Company Profile ==="]

    summary = profile.get("business_summary") or ""
    if summary:
        parts.append(f"Business: {summary}")

    segments = profile.get("revenue_segments") or []
    if segments:
        seg_strs = [f"{s.get('name') or '?'} ({s.get('pct_revenue') or '?'}%)" for s in segments]
        parts.append(f"Revenue: {', '.join(seg_strs)}")

    export = profile.get("export_split") or {}
    if export:
        dom = export.get("domestic_pct") or "?"
        exports = export.get("exports") or []
        exp_strs = [f"{e.get('market') or '?'} {e.get('pct_revenue') or '?'}%" for e in exports]
        market_str = f"{dom}% domestic"
        if exp_strs:
            market_str += f" | {', '.join(exp_strs)}"
        parts.append(f"Markets: {market_str}")

    chain = profile.get("supply_chain") or []
    if chain:
        chain_strs = [
            f"{c.get('input') or '?'} ({c.get('pct_cost') or '?'}% cost, from {', '.join(c.get('source_countries') or ['?'])})"
            for c in chain
        ]
        parts.append(f"Supply chain: {', '.join(chain_strs)}")

    macro = profile.get("macro_sensitivities") or []
    if macro:
        parts.append("Macro Sensitivities:")
        for s in macro:
            factor = s.get("factor") or "?"
            direction = s.get("direction") or "?"
            magnitude = s.get("magnitude") or "?"
            explanation = s.get("explanation") or ""
            parts.append(f"  {factor}: {direction} ({magnitude}) — {explanation}")

    reg = profile.get("regulatory_exposure") or []
    if reg:
        parts.append("Regulatory:")
        for r in reg:
            parts.append(
                f"  {r.get('policy') or '?'}: {r.get('impact') or '?'} — {r.get('description') or ''}"
            )

    comp = profile.get("competitive_position") or {}
    if comp:
        moat = comp.get("moat") or "?"
        share = comp.get("market_share") or "?"
        power = comp.get("pricing_power") or "?"
        parts.append(f"Competitive: Moat={moat}, Share={share}, Pricing={power}")

    return "\n".join(parts)


async def tool_get_macro_affected_tickers(factor: str) -> str:
    """Find tickers affected by a macro factor.

    Args:
        factor: Macro factor key (e.g. oil_price, usd_vnd, interest_rate,
                steel_price, iron_ore, china_demand, land_law).
    """
    if not factor:
        return "Error: no factor provided"

    from shared.neon import resolve_tickers_by_macro_factor

    try:
        results = await resolve_tickers_by_macro_factor(factor)
    except Exception as error:
        logger.warning("tool_get_macro_affected_tickers failed for %s: %s", factor, error)
        return f"Macro factor lookup unavailable for '{factor}': {error}"
    if not results:
        return f"No tickers with known sensitivity to '{factor}'."

    parts = [f"Tickers affected by {factor}:"]
    for r in results:
        ticker = r.get("ticker") or "?"
        direction = r.get("direction") or "?"
        magnitude = r.get("magnitude") or "?"
        explanation = r.get("explanation") or ""
        parts.append(f"  {ticker}: {direction} ({magnitude}) — {explanation}")
    return "\n".join(parts)
