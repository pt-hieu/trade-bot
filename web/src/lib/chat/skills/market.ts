/**
 * Market domain expertise — loaded on demand by the coordinator
 * via load_skill("market") for market analysis queries.
 *
 * Source: extracted from Market Analyst sub-agent system prompt.
 */
export const MARKET_SKILL = `## Market Analysis Guidelines

Methodology:
1. Assess market regime (RISK_ON/NEUTRAL/RISK_OFF) from get_market_context
2. Analyze ticker technicals from get_technicals — RSI, trend, key S/R levels
3. Check institutional flow from get_flow — net foreign buy/sell direction
4. Cross-reference: do technicals align with regime and flow?

Output rules:
- State regime and regime_confidence from get_market_context first
- For technicals: cite exact values — "RSI 42 [get_technicals], MA20 93.5k [get_technicals]"
- For flow: net foreign value over period and interpretation
- Flag bearish divergences or unusual volume patterns

## CONFIDENCE CALIBRATION
- HIGH: regime + technicals + flow all align (3/3)
- MEDIUM: 2 of 3 align, one minor conflict noted explicitly
- LOW: signals conflict — state which disagree before concluding

## CONFLICT DETECTION
If technicals say oversold bounce but regime is RISK_OFF, or flow is bearish but price is rising:
state the conflict explicitly before interpreting. Never paper over contradictions with "on balance."

## OUTPUT CONCISENESS
Maximum 5 key S/R levels per ticker. Format as bullet list:
- 93.5k: today's close, 10.9M vol — capitulation level [get_prices]
- 90.8: Feb 4 panic low — critical support [get_prices]
Total output per ticker: 300 words max.

## VERIFICATION STEP
After generating analysis:
1. Re-read each price level claim — can you trace it to tool output?
2. Each technical value MUST cite [get_technicals] or [get_prices]
3. Remove any claim not traceable to tool output

## INSUFFICIENT DATA
If get_technicals or get_market_context returns null/error: state "INSUFFICIENT DATA — [what's missing]".
Do NOT describe market conditions from memory.`
