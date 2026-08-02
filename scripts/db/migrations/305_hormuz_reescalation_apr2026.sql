-- Hormuz re-escalation: Trump declares unilateral strait blockade (2026-04-13)
--
-- Context: Mar 1 Hormuz closure played through immediate_shock (Mar 1-7),
-- sustained_pressure (Mar 8-31), then entered open-ended resolution_or_escalation
-- on Apr 1. On Apr 13, ceasefire talks collapsed and Trump unilaterally declared
-- a blockade of the Strait of Hormuz ("no ship will pass"). This is re-escalation
-- of the same crisis, not a new catalyst.
--
-- Approach: rewrite hormuz_closure_2026 phases in place. Historical immediate_shock
-- (Mar 1-7) is preserved as honest record of the original event. The new active
-- phase is sustained_pressure starting Apr 13 (today — market opens today) through
-- May 7, followed by resolution_or_escalation from May 8+.
--
-- Why sustained_pressure (not immediate_shock) for the new leg:
--   The operator explicitly requested a CAUTIOUS stance with high-R:R entries allowed,
--   not a full panic freeze. In shared/rules/geopolitical.py the phase config
--   maps immediate_shock → regime_floor=ELEVATED (mult 0.5) while sustained_pressure
--   → regime_floor=CAUTIOUS (mult 0.75). CAUTIOUS is what we want: defensive skew,
--   tighter R:R floor, but picks still flow through. Day-1 panic context is baked
--   into the behavior text rather than the phase severity.
--
-- Behavioral delta approved by the operator:
--   - Rewrite phases in place (not new catalyst)
--   - Cautious stance, allow high-R:R picks (no hard freeze)
--   - Start today (Apr 13), market opens today
--   - Account for TACO strategy (Trump often walks back maximalist declarations)

UPDATE catalysts
SET
  event = 'Trump declares unilateral US blockade of Strait of Hormuz after ceasefire talks collapse — re-escalation of Mar 2026 closure crisis',
  expected = 'Apr 13, 2026 - ongoing',
  confidence = 'MEDIUM',
  impact = 'NEGATIVE',
  notes = 'Ceasefire collapsed Apr 13, negotiations failed, Trump announces unilateral naval blockade ("no ship will pass"). Oil spike risk back on the table — $90-120+/bbl if enforced. TACO caveat: Trump has history of walking back maximalist declarations, so full impact may not materialize — size escalation accordingly. Day-1 reaction (today Apr 13): oil gap up, airlines (HVN, VJC) / steel (HPG, HSG) / plastics hit on cost push, energy names (GAS, PVS, PVD, BSR, PLX) may bid on sentiment. VND weakening + CPI re-acceleration risk if oil holds elevated through end-April. Stance: CAUTIOUS — do not hard-freeze entries, but require high R:R and defensive skew.',
  source = 'News update (2026-04-13): Trump declares blockade after ceasefire collapse',
  last_confirmed_at = NOW(),
  updated_at = NOW(),
  phases = '{
    "immediate_shock": {
      "impact": "NEGATIVE",
      "period": "Mar 1-7, 2026",
      "behavior": "Historical — original Mar 1 Hormuz closure panic window. Preserved for audit trail. Not active."
    },
    "sustained_pressure": {
      "impact": "NEGATIVE",
      "period": "Apr 13 - May 7, 2026",
      "behavior": "Trump blockade declared Apr 13 after ceasefire collapse — market opens today under re-escalation pressure. Day 1 (Apr 13): expect gap-down, oil spike, airlines/steel/plastics hit on cost push, energy names (GAS, PVS, PVD, BSR) bid on sentiment. Ongoing (Apr 14 - May 7): elevated oil (~$90-120 if enforced) pressures margins across transport/steel/plastics, CPI fears, VND weakness, defensive rotation to utilities/banks. Stance: CAUTIOUS — do NOT hard-block entries, allow high-R:R setups through (R:R ≥ 3.5 floor), reject marginal ones. Monitor TACO signal daily — Trump walkback triggers rapid mean-reversion, so avoid chasing panic and avoid over-committing to escalation thesis. Entries require wider stops and defensive sector bias. Avoid cyclicals with direct oil cost exposure unless R:R compensates."
    },
    "resolution_or_escalation": {
      "impact": "NEUTRAL",
      "period": "May 8, 2026+",
      "behavior": "Either Trump TACOs / diplomatic resolution → sharp recovery rally, oil unwinds, cyclicals snap back. Or blockade confirmed enforced → deeper selloff, defensive rotation, extended CPI/VND pressure. Directionality uncertain — maintain existing positions cautiously, avoid fresh geo-driven bets until catalyst resolves."
    }
  }'::jsonb
WHERE catalyst_key = 'hormuz_closure_2026';
