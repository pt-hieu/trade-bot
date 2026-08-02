-- Catalysts & Capital Events tables
-- Migrates hardcoded BASE_CATALYSTS / BASE_CAPITAL_EVENTS from Python dicts to DB

-- ── Catalysts ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS catalysts (
    id SERIAL PRIMARY KEY,
    catalyst_key VARCHAR(60) NOT NULL UNIQUE,
    event TEXT NOT NULL,
    expected VARCHAR(100) NOT NULL,
    affected_tickers TEXT[] NOT NULL DEFAULT '{}',
    impact VARCHAR(20) NOT NULL CHECK (impact IN ('POSITIVE', 'NEGATIVE', 'NEUTRAL')),
    confidence VARCHAR(10) NOT NULL CHECK (confidence IN ('HIGH', 'MEDIUM', 'LOW')),
    notes TEXT,
    source VARCHAR(500),
    phases JSONB,
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed')),
    outcome TEXT,
    actual_date VARCHAR(50),
    added_date DATE NOT NULL DEFAULT CURRENT_DATE,
    last_updated DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_catalysts_status ON catalysts(status);

CREATE INDEX IF NOT EXISTS idx_catalysts_affected ON catalysts USING GIN(affected_tickers);

-- ── Capital Events ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS capital_events (
    id SERIAL PRIMARY KEY,
    event_key VARCHAR(60) NOT NULL UNIQUE,
    ticker VARCHAR(20) NOT NULL,
    event_type VARCHAR(30) NOT NULL CHECK (event_type IN (
        'capital_increase', 'ipo', 'stock_split', 'ma', 'buyback', 'dividend'
    )),
    description TEXT NOT NULL,
    amount VARCHAR(100),
    expected_date VARCHAR(50) NOT NULL,
    dilution_pct FLOAT,
    impact VARCHAR(30) NOT NULL CHECK (impact IN (
        'POSITIVE', 'NEGATIVE_SHORT_TERM', 'NEGATIVE_LONG_TERM', 'WATCH'
    )),
    source VARCHAR(500),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed')),
    added_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_capital_events_status ON capital_events(status);

CREATE INDEX IF NOT EXISTS idx_capital_events_ticker ON capital_events(ticker);

-- ── Seed: Catalysts ────────────────────────────────────────────

INSERT INTO catalysts (catalyst_key, event, expected, affected_tickers, impact, confidence, notes, added_date, status, phases)
VALUES
(
    'crypto_licensing',
    'Crypto exchange license approvals',
    'Q1-Q2 2026',
    ARRAY['TCB', 'SSI', 'VIX', 'MBB', 'VPB'],
    'POSITIVE',
    'HIGH',
    'TCBS launched TCEX with VND 101B capital. MBBank partnered with Upbit.',
    '2026-01-26',
    'active',
    NULL
),
(
    'ftse_upgrade',
    'FTSE Emerging Market upgrade (frontier → secondary emerging)',
    'Sep 21, 2026',
    ARRAY['HPG', 'VCB', 'VIC', 'VHM', 'FPT', 'MSN', 'SAB', 'VNM',
          'SSI', 'VCI', 'VND', 'STB', 'DGC', 'KBC', 'VRE', 'PLX',
          'DXG', 'DIG', 'FRT', 'KDH', 'KDC', 'DPM', 'SHB', 'GEX',
          'EIB', 'VJC', 'HUT', 'VIX'],
    'POSITIVE',
    'HIGH',
    'Announced Oct 7, 2025. 28 stocks eligible for FTSE Emerging All Cap. VN weight: 0.34% EM All Cap, 0.22% EM Index. Passive ETF inflow est. $440M-$1.5B.',
    '2025-10-07',
    'active',
    '{"interim_review": {"period": "Mar 1-31, 2026", "impact": "POSITIVE", "behavior": "FTSE evaluates global broker access. Confirmation expected — low risk of reversal. Pre-positioning by active funds."}, "etf_rebalancing_prep": {"period": "Jul 1-Sep 20, 2026", "impact": "POSITIVE", "behavior": "Passive funds begin pre-positioning. Frontier ETFs sell VN stocks, EM ETFs accumulate. Expect increased foreign volume."}, "effective": {"period": "Sep 21+, 2026", "impact": "POSITIVE", "behavior": "Official inclusion in FTSE Emerging indices. Single-tranche frontier deletion, phased EM inclusion. Watch for sell the news risk."}}'
),
(
    'ftse_etf_rebalancing',
    'FTSE EM ETF passive rebalancing (VN inclusion)',
    'Sep 21, 2026',
    ARRAY['HPG', 'VCB', 'VIC', 'VHM', 'FPT', 'MSN', 'SAB', 'VNM',
          'SSI', 'VCI', 'VND', 'STB', 'DGC', 'KBC', 'VRE', 'PLX'],
    'POSITIVE',
    'HIGH',
    'Passive ETF inflow est. $440M-$1.5B (HSC/FPTS/TVS). ~1% of qualifying stocks market cap. Frontier ETFs will sell VN stocks simultaneously. Net passive impact modest — real upside is active fund flows.',
    '2026-02-13',
    'active',
    NULL
),
(
    'tet_holiday_2026',
    'Tet Holiday (Lunar New Year)',
    'Feb 14-22, 2026',
    ARRAY['VN-INDEX'],
    'NEUTRAL',
    'HIGH',
    'Market closed ~1 week. Pre-Tet profit-taking typical (1-2 weeks before). Post-Tet often sees red envelope rally optimism. Low liquidity window.',
    '2026-01-31',
    'active',
    '{"pre_tet": {"period": "Feb 1-13, 2026", "impact": "NEGATIVE", "behavior": "Profit-taking, cash accumulation for holiday spending"}, "closure": {"period": "Feb 14-22, 2026", "impact": "NEUTRAL", "behavior": "Market closed"}, "post_tet": {"period": "Feb 23+, 2026", "impact": "POSITIVE", "behavior": "Red envelope rally, renewed optimism, fresh capital inflows"}}'
)
ON CONFLICT (catalyst_key) DO NOTHING;

-- ── Seed: Capital Events ───────────────────────────────────────

INSERT INTO capital_events (event_key, ticker, event_type, description, amount, expected_date, dilution_pct, impact, source, added_date, status)
VALUES
(
    'MBS_capital_increase_2026',
    'MBS',
    'capital_increase',
    'MB Securities capital increase of VND 2.55 trillion',
    'VND 2.55 trillion',
    'mid-2026',
    15.0,
    'NEGATIVE_SHORT_TERM',
    'Company announcement',
    '2026-01-26',
    'pending'
),
(
    'VPBankS_IPO_2026',
    'VPBankS',
    'ipo',
    'VPBank Securities IPO to raise capital for crypto exchange',
    'TBD',
    '2026',
    NULL,
    'WATCH',
    'News reports',
    '2026-01-26',
    'pending'
)
ON CONFLICT (event_key) DO NOTHING;
