-- Core insert (columns from original migration 048)
INSERT INTO catalysts
    (catalyst_key, event, expected, affected_tickers, impact, confidence,
     notes, source, status, added_date, phases)
VALUES
    (
        'hormuz_closure_2026',
        'Iran closes Strait of Hormuz after US-Israel strikes — oil spike risk $120+/bbl',
        'Mar 1, 2026 - ongoing',
        ARRAY['HVN', 'VJC', 'PLX', 'PVD', 'PVS', 'GAS', 'BSR', 'OIL', 'HPG', 'HSG'],
        'NEGATIVE',
        'HIGH',
        'Oil ~$70 to $120+. VND weakening, inflation risk. Defensive: energy (GAS, PVD, PVS) may benefit. Pain: airlines (HVN, VJC), steel (HPG, HSG), plastics.',
        'Al Jazeera liveblog',
        'active',
        CURRENT_DATE,
        '{"immediate_shock": {"period": "Mar 1-7, 2026", "impact": "NEGATIVE", "behavior": "Panic selling, oil gap up, airline/steel hammered. Energy names may spike on sentiment."}, "sustained_pressure": {"period": "Mar 8-31, 2026", "impact": "NEGATIVE", "behavior": "Sustained high oil prices pressure margins across transport, steel, plastics. CPI fears. VND under pressure."}, "resolution_or_escalation": {"period": "Apr 2026+", "impact": "NEUTRAL", "behavior": "Diplomatic resolution leads to sharp recovery rally. Escalation leads to deeper selloff, defensive rotation to utilities/banks."}}'::jsonb
    )
ON CONFLICT (catalyst_key) DO NOTHING
