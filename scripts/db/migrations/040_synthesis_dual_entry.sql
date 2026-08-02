-- 040: Add dual entry (support vs market) instructions to synthesis prompt
-- When current price is >1.5% above nearest support, show both limit and market entries
-- so the trader can decide: wait for pullback (higher R:R) or buy now (lower R:R)

UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    E'- If no pre-computed candidates exist, fall back to calling tool_calculate_trade_setup yourself',
    E'- If no pre-computed candidates exist, fall back to calling tool_calculate_trade_setup yourself\n\n## DUAL ENTRY: Support vs Market Entry\nPre-computed picks may include a `market_setup` field when current price is >1.5% above support:\n- Default entry/stop/target = LIMIT ORDER at support (may require pullback)\n- `market_setup` = BUY NOW at current price with adjusted R:R\n- Present BOTH options in TOP PICKS when market_setup exists:\n  * \"Entry 50.0k (limit at support) | R:R 5.6:1 — OR — Entry 52.0k (market) | R:R 1.2:1\"\n- If market_setup.valid is false (R:R < 3.0), note: \"Market entry does not meet R:R threshold\"\n- If ONLY market_setup is valid, skip the support entry framing\n- This helps the trader decide: wait for pullback (higher R:R) or act now (lower R:R)'
)
WHERE agent_key = 'synthesis';
