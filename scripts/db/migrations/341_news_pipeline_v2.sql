-- 341_news_pipeline_v2.sql
--
-- News Pipeline v2 schema additions + COMPANY_TICKERS alias backfill +
-- 90-day article reset. See SWI-241 / SWI-242.
--
-- 1. company_profiles.aliases TEXT[] (GIN) — Stage 1 receives the universe
--    table with aliases so an LLM that has no parametric knowledge of VN
--    listings can still resolve "Becamex" → BCM, "Hoà Phát" → HPG.
--
-- 2. narratives.pipeline_version + catalysts.pipeline_version — soft-archive
--    cutover. v1 rows stay queryable; v2 reads filter pipeline_version='v2'
--    via shared/neon helpers.
--
-- 3. articles.stage1_verdict JSONB — Stage 1 routing decision persisted for
--    audit re-tag (per the design-challenge "drop-bucketing parity" finding).
--
-- 4. Backfill aliases from the legacy `COMPANY_TICKERS` dict
--    (scripts/shared/ticker_extract.py:16-211) so the dict can be deleted in
--    the cutover commit. UPDATE-only on existing company_profiles rows; the
--    FK to stocks(ticker) means we cannot create profiles for unlisted codes.
--
-- 5. 90d article reset — null affected_tickers / sentiment_score /
--    sentiment_tickers / narrative_id for articles published in the last
--    90 days, so v2 re-tags them cleanly. Older articles stay frozen.

BEGIN;

-- 1. Schema changes ---------------------------------------------------------

ALTER TABLE company_profiles
    ADD COLUMN IF NOT EXISTS aliases TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];

CREATE INDEX IF NOT EXISTS idx_cp_aliases
    ON company_profiles USING gin (aliases);

ALTER TABLE narratives
    ADD COLUMN IF NOT EXISTS pipeline_version VARCHAR(8) NOT NULL DEFAULT 'v1';

CREATE INDEX IF NOT EXISTS idx_narratives_pipeline_version
    ON narratives (status, pipeline_version);

ALTER TABLE catalysts
    ADD COLUMN IF NOT EXISTS pipeline_version VARCHAR(8) NOT NULL DEFAULT 'v1';

CREATE INDEX IF NOT EXISTS idx_catalysts_pipeline_version
    ON catalysts (status, pipeline_version);

ALTER TABLE articles
    ADD COLUMN IF NOT EXISTS stage1_verdict JSONB;

COMMENT ON COLUMN company_profiles.aliases IS
    'Brand / Vietnamese / English alias tokens for ticker disambiguation '
    'during news Stage 1 entity spotting. Backfilled in 341 from the legacy '
    'COMPANY_TICKERS dict; ongoing curation via aliases-runbook follow-up.';

COMMENT ON COLUMN narratives.pipeline_version IS
    'Soft-archive marker. v1 = legacy 5-stage pipeline; v2 = SWI-241 redesign. '
    'Read-side helpers in shared/neon/narratives.py filter to v2 only.';

COMMENT ON COLUMN catalysts.pipeline_version IS
    'Soft-archive marker. v1 = legacy news_pipeline.py path; v2 = SWI-241 '
    'two-stage extractor. Read-side helpers filter to v2 only.';

COMMENT ON COLUMN articles.stage1_verdict IS
    'Stage 1 (news_relevance) raw verdict: is_vn_relevant, candidate_entities, '
    'relevance_confidence, abstain_reason. Persisted for audit re-tag.';

-- 2. Aliases backfill -------------------------------------------------------
-- One row per ticker present in the COMPANY_TICKERS dict
-- (scripts/shared/ticker_extract.py:16-211). UPDATE-only — the FK to
-- stocks(ticker) means tickers absent from `stocks` (VNZ, VAC, FOX, TTN, KSF,
-- OIL, EVN, MAS, VPS, etc.) are filtered out by the JOIN. The cutover commit
-- deletes the COMPANY_TICKERS dict; surviving aliases live here.

WITH alias_data(ticker, aliases) AS (VALUES
    ('ABB', ARRAY['abbank']),
    ('ACB', ARRAY['acb','asia commercial bank']),
    ('BID', ARRAY['bidv']),
    ('BAB', ARRAY['bắc á bank','bac a bank']),
    ('CTG', ARRAY['vietinbank']),
    ('EIB', ARRAY['eximbank']),
    ('HDB', ARRAY['hd bank','hdbank']),
    ('KLB', ARRAY['kienlongbank','kien long bank']),
    ('LPB', ARRAY['lienvietpostbank','lpbank']),
    ('MSB', ARRAY['maritime bank','msb']),
    ('MBB', ARRAY['mb bank','mbbank','military bank']),
    ('NAB', ARRAY['nam a bank']),
    ('NCB', ARRAY['ncb']),
    ('OCB', ARRAY['ocb','orient commercial bank']),
    ('STB', ARRAY['sacombank']),
    ('SGB', ARRAY['saigonbank']),
    ('SSB', ARRAY['seabank','seabbank']),
    ('SHB', ARRAY['shb']),
    ('TCB', ARRAY['techcombank']),
    ('TPB', ARRAY['tienphong bank','tpbank']),
    ('VCB', ARRAY['vietcombank']),
    ('VBB', ARRAY['vietbank']),
    ('VIB', ARRAY['vib','vietnam international bank']),
    ('VPB', ARRAY['vpbank']),
    ('BCM', ARRAY['becamex']),
    ('CII', ARRAY['cii','ho chi minh infrastructure']),
    ('DIG', ARRAY['dic corp']),
    ('DXG', ARRAY['đất xanh','dat xanh']),
    ('DXS', ARRAY['dat xanh services','đất xanh services']),
    ('HDG', ARRAY['hà đô','ha do']),
    ('HAG', ARRAY['hoang anh gia lai','hoàng anh gia lai']),
    ('KBC', ARRAY['kbc','kinh bac city']),
    ('KDH', ARRAY['khang điền','khang dien']),
    ('NLG', ARRAY['nam long']),
    ('NVL', ARRAY['novaland']),
    ('PDR', ARRAY['phat dat','phát đạt']),
    ('SZC', ARRAY['sonadezi']),
    ('KSF', ARRAY['sunshine group','sun group']),
    ('SSH', ARRAY['sunshine homes']),
    ('VPI', ARRAY['van phu invest','văn phú invest']),
    ('VHM', ARRAY['vinhomes']),
    ('VRE', ARRAY['vincom retail']),
    ('VPL', ARRAY['vinpearl']),
    ('CMG', ARRAY['cmc corp','cmg']),
    ('DGW', ARRAY['digiworld']),
    ('ELC', ARRAY['elcom']),
    ('FPT', ARRAY['fpt corporation','fpt']),
    ('FOX', ARRAY['fpt telecom','fpt play']),
    ('TTN', ARRAY['vnpt']),
    ('VNZ', ARRAY['vng corporation']),
    ('MWG', ARRAY['bách hoá xanh','bach hoa xanh','bách hóa xanh','mobile world','thế giới di động']),
    ('DBC', ARRAY['dabaco']),
    ('FRT', ARRAY['fpt retail','long chau','nhà thuốc long châu']),
    ('MSN', ARRAY['masan']),
    ('MCH', ARRAY['masan consumer','ngành hàng tiêu dùng masan']),
    ('PNJ', ARRAY['pnj','phú nhuận jewelry','phu nhuan jewelry']),
    ('SAB', ARRAY['sabeco','saigon beer']),
    ('VNM', ARRAY['vinamilk']),
    ('VSN', ARRAY['vissan']),
    ('BSR', ARRAY['binh son refinery','bình sơn']),
    ('PVD', ARRAY['petrovietnam drilling','pv drilling']),
    ('GAS', ARRAY['petrovietnam gas','pv gas','pvgas']),
    ('PLX', ARRAY['petrolimex']),
    ('POW', ARRAY['pv power','pvpower']),
    ('OIL', ARRAY['pv oil','pvoil']),
    ('PVS', ARRAY['pvs','petrovietnam technical services']),
    ('PVT', ARRAY['pvt','petrovietnam transportation']),
    ('GVR', ARRAY['cao su vietnam','vietnam rubber']),
    ('DCM', ARRAY['dam ca mau','đạm cà mau']),
    ('DPM', ARRAY['dam phu my','đạm phú mỹ']),
    ('DGC', ARRAY['dgc','duc giang chemicals','đức giang']),
    ('HPG', ARRAY['hoa phat','hòa phát','hoa phat industrial']),
    ('HSG', ARRAY['hoa sen group','hoa sen']),
    ('HBC', ARRAY['hoa binh construction']),
    ('NKG', ARRAY['nam kim','thep nam kim','thép nam kim']),
    ('VGC', ARRAY['viglacera']),
    ('HT1', ARRAY['vicem ha tien','xi mang ha tien']),
    ('GMD', ARRAY['gemadept','gemalink']),
    ('HVN', ARRAY['vietnam airlines']),
    ('VJC', ARRAY['vietjet','vietjet air']),
    ('VIC', ARRAY['vingroup']),
    ('HCM', ARRAY['hcm securities','ho chi minh securities']),
    ('MAS', ARRAY['mirae asset']),
    ('SSI', ARRAY['ssi securities','ssi']),
    ('VCI', ARRAY['vci securities','viet capital securities']),
    ('VND', ARRAY['vndirect','vnd securities']),
    ('VIX', ARRAY['vix securities']),
    ('VPS', ARRAY['vps securities']),
    ('BVH', ARRAY['bảo việt','bao viet']),
    ('BMI', ARRAY['bảo minh','bao minh']),
    ('PVI', ARRAY['pvi','petrovietnam insurance']),
    ('EVN', ARRAY['evn','điện lực']),
    ('PC1', ARRAY['pc1','pc1 group','power construction no 1']),
    ('NT2', ARRAY['phu my 3','nhon trach 2']),
    ('ACV', ARRAY['acv','airports corporation vietnam']),
    ('IMP', ARRAY['imexpharm']),
    ('TRA', ARRAY['traphaco']),
    ('DMC', ARRAY['domesco']),
    ('DHG', ARRAY['dhg pharma']),
    ('TMS', ARRAY['transimex']),
    ('HAH', ARRAY['hai an','hải an']),
    ('VAC', ARRAY['dat viet vac']),
    ('FIT', ARRAY['fit group']),
    ('HQC', ARRAY['hqc']),
    ('GEX', ARRAY['gelex']),
    ('GEE', ARRAY['geleximco']),
    ('REE', ARRAY['refrigeration electrical engineering','ree corp','ree']),
    ('ITA', ARRAY['tan tao']),
    ('TCT', ARRAY['tct'])
)
INSERT INTO company_profiles (ticker, source, aliases)
SELECT a.ticker, 'alias_backfill_v2', a.aliases
FROM alias_data a
JOIN stocks s ON s.ticker = a.ticker
ON CONFLICT (ticker) DO UPDATE
    SET aliases = ARRAY(
            SELECT DISTINCT UNNEST(
                COALESCE(company_profiles.aliases, ARRAY[]::TEXT[])
                || EXCLUDED.aliases
            )
        ),
        updated_at = NOW();

-- 3. 90-day article reset ---------------------------------------------------

UPDATE articles
   SET affected_tickers = NULL,
       sentiment_score = NULL,
       sentiment_tickers = NULL,
       sentiment_confidence = NULL,
       narrative_id = NULL,
       stage1_verdict = NULL
 WHERE published_at >= NOW() - INTERVAL '90 days';

-- 4. Migration ledger -------------------------------------------------------

INSERT INTO schema_migrations (version)
VALUES ('341_news_pipeline_v2')
ON CONFLICT (version) DO NOTHING;

COMMIT;
