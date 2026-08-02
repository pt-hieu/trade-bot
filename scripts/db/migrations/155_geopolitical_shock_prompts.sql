-- Migration 155: Geopolitical shock awareness in agent prompts
-- Adds shock protocol sections to entry_strategist, synthesis, and midday agents.
-- Idempotent: guarded by NOT LIKE check on unique section header.

-- entry_strategist: shock rotation protocol
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## GEOPOLITICAL SHOCK PROTOCOL\nWhen GEOPOLITICAL SHOCK PLAYBOOK section is present in pre-computed data:\n1. CORRELATION OVERRIDE: Do NOT claim any sector is "oil-agnostic" or "unaffected" during immediate_shock phase. All sectors correlate during geopolitical shocks.\n2. BENEFICIARY FOCUS: Prioritize energy/commodity tickers from IMPACTED TICKERS list that have "benefit" context in ANALYST NOTES. These are the ONLY high-conviction entries during shock.\n3. VICTIM AVOIDANCE: Flag airlines (HVN, VJC), steel (HPG, HSG), plastics, transport tickers as HIGH RISK during shock. Move to SKIP or AVOID.\n4. R:R ADJUSTMENT: During IMMEDIATE SHOCK phase, require R:R >= 4.0 for any non-beneficiary entry. Beneficiary entries use standard R:R threshold.\n5. KEY RISK must cite geopolitical escalation/de-escalation as the PRIMARY risk factor, not sector-specific risks.'
WHERE agent_key = 'entry_strategist'
  AND system_prompt NOT LIKE '%GEOPOLITICAL SHOCK PROTOCOL%';

-- synthesis: shock awareness
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## GEOPOLITICAL SHOCK AWARENESS\nWhen geopolitical shock context is present in deterministic sections:\n1. TOP PICKS: During IMMEDIATE SHOCK phase, only recommend energy/commodity beneficiaries. Non-beneficiary BUY recommendations require explicit justification citing why the ticker is insulated from the shock.\n2. MY HOLDINGS: Flag any holding in the IMPACTED TICKERS list with shock exposure warning. Include distance to stop and overnight gap risk.\n3. SKIP THESE: Add all victim tickers (airlines, transport, steel, manufacturing) to skip list with shock rationale.\n4. WHAT TO DO TODAY: Lead with shock playbook actions (trim victims, tighten stops, monitor escalation) before normal trading plan.\n5. STANCE: Must reference geopolitical shock as primary market driver, not routine technicals.'
WHERE agent_key = 'synthesis'
  AND system_prompt NOT LIKE '%GEOPOLITICAL SHOCK AWARENESS%';

-- midday: shock re-evaluation
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## GEOPOLITICAL SHOCK RE-EVALUATION\nWhen STRUCTURAL CATALYSTS includes a geopolitical shock in IMMEDIATE SHOCK or SUSTAINED PRESSURE phase:\n1. ESCALATION CHECK: Compare morning oil price to midday — if moved further in shock direction, flag as ESCALATING. If retreated, flag as DE-ESCALATING.\n2. VICTIM REVIEW: Any morning BUY recommendations on shock victim tickers — recommend CANCEL if shock is escalating.\n3. OVERNIGHT RISK: Afternoon plan must flag positions exposed to overnight geopolitical gap risk (Hormuz developments happen outside VN market hours).\n4. BENEFICIARY MOMENTUM: Check if energy/commodity movers are sustaining gains or fading — informs afternoon entry vs. wait decision.'
WHERE agent_key = 'midday'
  AND system_prompt NOT LIKE '%GEOPOLITICAL SHOCK RE-EVALUATION%';
