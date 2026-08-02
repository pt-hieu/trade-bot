"""Shared error-emission helpers for the broker layer.

Post-SWI-180: consumed by ``native_tools._wrap_with_policy`` (and by the
registry's ``format_tool_schemas`` legacy renderer) to surface a consistent
self-correcting error shape.
"""

# Old tool_ names → broker domain hints for self-correcting error messages.
_OLD_TOOL_NAME_HINTS: dict[str, str] = {
    "search_articles": "article.search",
    "read_article": "article.read",
    "list_articles": "article.search",
    "get_holdings": "portfolio.get_watchlist",
    "get_trades": "portfolio.get_trades",
    "get_learnings": "portfolio.get_learnings",
    "get_catalyst_preview": "portfolio.get_longterm_config",
    "get_catalysts": "portfolio.get_longterm_config",
    "get_technicals": "technical.get_technicals",
    "get_ticker_data": "technical.get_technicals",
    "get_flow": "enrichment.get_flow",
    "get_insider": "enrichment.get_insider",
    "get_relative_strength": "enrichment.get_relative_strength",
    "get_valuation": "fundamental.get_valuation",
    "get_belief_accuracy": "belief.get_accuracy",
    "get_active_narratives": "narrative.get_active",
    "get_rotation": "market.get_rotation",
    "get_sector_data": "market.get_sector_data",
    "position_scale": "portfolio.get_position_scale",
    "get_stats": "statistic.get_stats",
}


def suggest_broker_name(query: str) -> str:
    """Match old tool_ names in a query and return a corrective hint, or empty string."""
    query_lower = query.lower().replace("tool_", "")
    for old_suffix, broker_name in _OLD_TOOL_NAME_HINTS.items():
        if old_suffix in query_lower:
            return (
                f"Did you mean '{broker_name}'? Use call_tools directly: "
                f'call_tools([{{"name": "{broker_name}", "args": {{...}}}}]).'
            )
    return ""


def unknown_tool_error(name: str) -> dict[str, str]:
    """Build the error payload for an unknown or blank tool name.

    Emits a coaching JSON when ``name`` is blank so the model sees a valid
    tool exemplar — the old ``"Unknown tool: "`` with no suffix left the
    model with zero diagnostic info. Consumed by ``native_tools.unlock_tool``
    and ``registry.format_tool_schemas``.
    """
    stripped = name.strip() if name else ""
    if not stripped:
        return {
            "error": (
                "Empty call payload — every entry in 'calls' must include a "
                "non-blank 'name'. Example: "
                'call_tools([{"name": "fundamental.get_valuation", '
                '"args": {"tickers": ["FPT"]}}]).'
            ),
        }
    hint = suggest_broker_name(stripped)
    message = f"Unknown tool: {stripped}"
    if hint:
        message += f". {hint}"
    return {"error": message}
