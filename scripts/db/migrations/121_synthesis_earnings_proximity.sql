-- Migration 121: Add earnings proximity awareness to synthesis agent
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## Earnings Proximity Rule\nWhen a TOP PICK has earnings_warning or a TickerContext shows "EARNINGS:" alert:\n- Add visible caution note in the pick recommendation\n- Within 7 days of filing: recommend half-size entry with note "Earnings expected [quarter] — half size until filed"\n- Do NOT skip the pick entirely — earnings proximity is a sizing concern, not a veto'
WHERE agent_key = 'synthesis'
AND system_prompt NOT LIKE '%Earnings Proximity Rule%';
