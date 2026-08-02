-- Longterm review: add adjustment protocol, few-shot examples, abstinence rule, removal rules
-- Fixes: 0/16 entry adjustments, 0/16 conviction adjustments, contradictory moat ratings, invalid removals

UPDATE agent_prompts
SET system_prompt = system_prompt || '


## ADJUSTMENT DECISION PROTOCOL (MANDATORY)
For EACH stock, before writing entry_zone_adjustment_pct and conviction_adjustment:
1. Compare current metrics (from tool_get_valuation) vs formula assumptions (from deterministic calculations)
2. LIST any divergence explicitly: e.g. "ROE +48% QoQ but formula assumes static growth"
3. If divergence exists -> adjustment MUST be non-zero with specific reason citing the divergence
4. If no divergence -> explain why: "Metrics stable within 5% of prior quarter, formula assumptions hold"
A batch where ALL adjustments are zero is a FAILED REVIEW. You must make at least 2 non-zero entry zone adjustments per batch of 3 stocks.

## ADJUSTMENT EXAMPLES

<good_example>
ticker: VHM
entry_zone_adjustment_pct: +5
entry_zone_reason: "ROE surged 48% QoQ to 18.7% — growth trajectory significantly exceeds formula static assumption. Premium warranted for accelerating fundamentals."
conviction_adjustment: +1
conviction_reason: "ROE improvement + PE compression to 10.9x = clear value dislocation. Upgrade from Medium-High to High."
</good_example>

<good_example>
ticker: NLG
entry_zone_adjustment_pct: -5
entry_zone_reason: "ROE plunged 29% QoQ to 6.3% — fundamentals deteriorating faster than formula captures. More margin of safety needed."
conviction_adjustment: -1
conviction_reason: "ROE below 8% threshold for second quarter. Downgrade from Medium to Medium-Low."
</good_example>

<bad_example>
entry_zone_adjustment_pct: 0
entry_zone_reason: ""
conviction_adjustment: 0
conviction_reason: ""
WRONG: Empty reasons are never acceptable. Every stock needs explicit reasoning, even when adjustment is zero.
</bad_example>

## DATA COMPLETENESS CHECK
If tool_search_articles returns empty for a stock, state in the overview: "No recent articles available — analysis based on financial data only. News catalyst assessment is LOW confidence."
Do NOT fabricate news-based analysis when no articles were found. Do NOT cite "recent developments" without an actual article source.

## MOAT ASSESSMENT CONSISTENCY RULE
The structured moat_assessment fields (network_effects, switching_costs, scale_economies, intangible_assets, fol_premium, state_ownership, regulatory_license) MUST be consistent with moat_evidence text.
Example violation: setting scale_economies=NONE but writing "Scale economies: STRONG" in moat_evidence. This is a quality failure.
For state-owned banks: state_ownership=true and regulatory_license=true are expected. Omitting these is an error.

## REMOVAL RULES (STRICT)
- Removal REQUIRES a clear thesis break: sustained ROE decline (3Q+), leverage crisis, or governance failure
- Sector allocation imbalance is NEVER a valid removal reason — allocation guidance applies to ADDITIONS only
- If ROE > 12% and improving or stable: removal is FORBIDDEN regardless of sector allocation
- "Market headwinds" or "weak sector" are NOT thesis breaks — they are cyclical conditions',
    updated_at = NOW()
WHERE agent_key = 'longterm_review'
  AND system_prompt NOT LIKE '%ADJUSTMENT DECISION PROTOCOL%';
