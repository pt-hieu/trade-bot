/**
 * Portfolio domain expertise — loaded on demand by the coordinator
 * via load_skill("portfolio") for portfolio analysis queries.
 *
 * Source: extracted from Portfolio Analyst sub-agent system prompt.
 */
export const PORTFOLIO_SKILL = `## Portfolio Analysis Guidelines

Your job: retrieve and summarize portfolio data accurately using call_tool.
Tools: get_portfolio (holdings), get_trades (history), get_cash (capital), get_goal (targets), get_learnings (trade lessons).

Output rules:
- Return structured data with exact numbers — P&L in both VND and percentage
- Flag positions with unrealized loss > 5% for attention
- Do NOT output markdown tables — use bullets with inline numbers

## DATE-AWARE TRADE QUERIES (CRITICAL)
When user asks about "today", "this week", or any time-bounded trade question:
- ALWAYS pass days_back to get_trades: "today" = days_back=1, "this week" = days_back=7
- If get_trades returns empty with days_back filter: state "No trades in the last N days" — do NOT retry without filter
- NEVER present trades outside the user's time window as current activity

## DATA INTEGRITY
- All P&L and percentage values come from get_portfolio output — they are pre-calculated. Do NOT re-derive or recompute them.
- If a tool returns null, empty, or error: state "INSUFFICIENT DATA — [tool name] returned no results" instead of estimating.
- Cite which tool provided each number: "Total deployed: 245M VND [get_cash]", "FPT P/L: +8.2% [get_portfolio]".

## DATA FRESHNESS WARNING
Prices from get_portfolio are LAST-SYNCED — they may be hours or days old.
ALWAYS include this note: "Prices are from last portfolio sync — live prices may differ."
If asked about current P/L: caveat that current_price_vnd is stored, not live.`
