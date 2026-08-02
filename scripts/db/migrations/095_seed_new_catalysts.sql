-- Migration 095: Seed new catalysts and capital events for 2026
-- Date: 2026-02-22

-- ── New Catalysts ────────────────────────────────────────────────────────────

INSERT INTO catalysts
    (catalyst_key, event, expected, affected_tickers, impact, confidence,
     notes, source, status, added_date, discovery_source)
VALUES
    (
        'public_investment_2026',
        'Government 95% public investment disbursement target 2026',
        'Q1-Q4 2026 (accelerated disbursement)',
        ARRAY['HPG', 'CTD', 'HHV', 'VCG', 'DIG', 'C4G'],
        'POSITIVE',
        'HIGH',
        'Gov set 95% disbursement target vs ~72% actual in 2025. Infrastructure surge benefits steel, construction, highways.',
        'Government Resolution 2026',
        'active',
        CURRENT_DATE,
        'seed_095'
    ),
    (
        'fdi_industrial_2026',
        'Record FDI inflows driving industrial real estate demand',
        'H1 2026 (ongoing)',
        ARRAY['KBC', 'IDC', 'SZC', 'BCM', 'LHG'],
        'POSITIVE',
        'HIGH',
        'FDI at record highs post-FTSE announcement. Industrial park occupancy rising. Factory construction backlog growing.',
        'MPI FDI Report 2025-2026',
        'active',
        CURRENT_DATE,
        'seed_095'
    ),
    (
        'bank_npl_resolution_2026',
        'Circular 06 NPL restructuring extension — banking sector relief',
        'Q1-Q2 2026',
        ARRAY['VPB', 'STB', 'SHB', 'LPB', 'TCB'],
        'POSITIVE',
        'MEDIUM',
        'SBV extended Circular 06 allowing banks to restructure pandemic-era NPLs without full provisioning. Reduces pressure on weaker banks.',
        'SBV Circular 06 Extension',
        'active',
        CURRENT_DATE,
        'seed_095'
    ),
    (
        'real_estate_law_2026',
        'New Land Law and Real Estate Business Law full implementation',
        'Q1-Q2 2026',
        ARRAY['VHM', 'NLG', 'KDH', 'DIG', 'DXG'],
        'POSITIVE',
        'HIGH',
        'Laws took effect Jan 1, 2026. Clearer land use rights, faster approval processes. Unblocks stalled projects. Positive for developers with land banks.',
        'Land Law 2024 / Real Estate Business Law 2024',
        'active',
        CURRENT_DATE,
        'seed_095'
    ),
    (
        'msci_fm_review_2026',
        'MSCI Frontier Markets semi-annual index review',
        'May 2026 (announcement), Jun 2026 (effective)',
        ARRAY['VN-INDEX'],
        'NEUTRAL',
        'MEDIUM',
        'Routine MSCI FM review. VN weight stable. Main risk: foreign room exhaustion triggers re-weighting. Watch for any changes to FM index.',
        'MSCI Index Review Schedule',
        'active',
        CURRENT_DATE,
        'seed_095'
    )
ON CONFLICT (catalyst_key) DO NOTHING;

-- ── New Capital Events ───────────────────────────────────────────────────────

INSERT INTO capital_events
    (event_key, ticker, event_type, description, amount, expected_date,
     dilution_pct, impact, source, status, added_date, discovery_source)
VALUES
    (
        'SSI_capital_increase_2026',
        'SSI',
        'capital_increase',
        'SSI Securities planned capital increase via share issuance to fund expansion ahead of FTSE upgrade. Higher capital base to capture institutional flow.',
        '500B VND',
        'H1 2026',
        15.0,
        'NEGATIVE_SHORT_TERM',
        'SSI AGM 2025 / Investor Relations',
        'pending',
        CURRENT_DATE,
        'seed_095'
    ),
    (
        'VIX_capital_increase_2026',
        'VIX',
        'capital_increase',
        'VIX Investment & Securities capital increase to strengthen balance sheet. Targeting tech infrastructure investment ahead of market structure upgrade.',
        '300B VND',
        'H1 2026',
        20.0,
        'NEGATIVE_SHORT_TERM',
        'VIX AGM 2025 / Investor Relations',
        'pending',
        CURRENT_DATE,
        'seed_095'
    )
ON CONFLICT (event_key) DO NOTHING;
