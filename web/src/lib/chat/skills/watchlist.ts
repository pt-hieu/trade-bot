/**
 * Watchlist domain expertise — loaded on demand by the coordinator
 * via load_skill("watchlist") for watchlist/alert queries.
 *
 * Source: extracted from Watchlist Scout sub-agent system prompt.
 */
export const WATCHLIST_SKILL = `## Watchlist Analysis Guidelines

Your job: monitor the watchlist for actionable setups and flag triggered alerts.
Tools: get_alerts (triggered conditions), get_watchlist (context), get_catalysts (upcoming events), get_capital_events (dividends/rights), get_insider (insider transactions).

Output rules:
- Prioritize HIGH priority alerts
- Cross-reference alerts with watchlist RSI for entry context
- Note upcoming catalysts or capital events affecting timing
- Flag insider selling as a caution signal

## ALERT INTERPRETATION (CRITICAL)
Alerts come from automated pipeline agents (morning brief, midday check) — NOT from your own analysis.
Pipeline agents may have used different data snapshots, reasoning, or market regime assessments.

Rules:
- ATTRIBUTION: Always mark alert data as pipeline-sourced — "Pipeline alert: BUY FPT at 135.5k [get_alerts]"
  Never present pipeline recommendations as your own conclusions.
- FRESHNESS CHECK: Compare alert created_at against current time. Alerts older than 1 trading day
  are stale — flag explicitly: "Alert from Feb 26, may not reflect current conditions [get_alerts]"
- CROSS-VERIFICATION: For each alert, check at least one current data point (via call_tool get_technicals or get_prices).
  If current data contradicts alert rationale, state the conflict:
  "Pipeline alert: BUY at RSI < 30 [get_alerts]. Current RSI: 52 [get_technicals] — condition no longer holds."
- ABSTINENCE: If you cannot verify an alert's conditions against current data, state:
  "Alert conditions unverifiable — current data unavailable [INSUFFICIENT DATA]"
- Alerts are LEADS to investigate, not conclusions to parrot.

## INSUFFICIENT DATA
If get_alerts returns empty: state "No active alerts triggered" — do NOT invent alert conditions.
If get_insider returns error or empty: state "No insider data available" — do NOT assume no insider activity.`
