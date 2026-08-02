-- SWI-74 manual dedup: collapse residual same-event narratives that
-- migration 337's automated cosine+ticker-overlap rule did not reach.
--
-- Each pair below was hand-verified against `summary` text. Survivor
-- chosen by editorial judgment (article_count for big stories, conviction
-- otherwise). Losers get status='stale', maturity='stale', merged_into=
-- winner.id, plus a "SWI-74 manual dedup (2026-05-01): merged into …"
-- marker appended to summary for audit traceability.

BEGIN;

CREATE TEMP TABLE swi74_pairs (
    loser_key  text PRIMARY KEY,
    winner_key text NOT NULL
) ON COMMIT DROP;

INSERT INTO swi74_pairs (loser_key, winner_key) VALUES
    -- USD/VND rise — same event, conv-DESC winner
    ('dollar_edges_up_dong',                       'dollar_strengthens_against_dong'),
    -- Gold price decline cluster (all sentiment-negative or neutral)
    ('gold_prices_fall',                           'gold_price_plunge'),
    ('sjc_gold_price_plunge',                      'gold_price_plunge'),
    ('vietnam_gold_prices_drop_divergence',        'gold_price_plunge'),
    ('vietnam_gold_ring_prices_decline',           'gold_price_plunge'),
    ('gold_price_stalling_major_selling_pressure', 'gold_price_plunge'),
    -- Pakistan-mediated US-Iran talks (id-ASC tiebreak; both equal otherwise)
    ('pakistan_us_iran_talks_guarantees',          'pakistan_us_iran_talks'),
    -- Vietnam-China state visit Apr 2026 (32 cooperation docs signed during it)
    ('vietnam_china_32_cooperation_documents',     'vietnam_china_state_visit_april_2026'),
    -- Vietnam double-digit GDP push for 2026
    ('double_digit_growth_policy_push',            'vietnam_gdp_q1_2026_double_digit_goal'),
    ('vietnam_gdp_growth_model_implementation',    'vietnam_gdp_q1_2026_double_digit_goal'),
    ('vietnam_double_digit_growth_target',         'vietnam_gdp_q1_2026_double_digit_goal'),
    -- Hanoi Nguyen Trai project groundbreaking (GVR is the developer)
    ('hanoi_nguyen_trai_project_groundbreaking',   'gvr_nguyen_trai_project_update'),
    -- Strait of Hormuz blockage cluster (only same-direction sentiment merged)
    ('iran_hormuz_traffic_halt',                   'strait_hormuz_oil_blockage'),
    ('iran_hormuz_strait_closure',                 'strait_hormuz_oil_blockage');

-- Resolve loser/winner ids; abort if any key is missing or already stale.
CREATE TEMP TABLE swi74_resolved AS
SELECT p.loser_key,
       p.winner_key,
       l.id AS loser_id,
       w.id AS winner_id
FROM swi74_pairs p
JOIN narratives l ON l.narrative_key = p.loser_key  AND l.status = 'active'
JOIN narratives w ON w.narrative_key = p.winner_key AND w.status = 'active';

DO $$
DECLARE expected int; resolved int;
BEGIN
    SELECT COUNT(*) INTO expected FROM swi74_pairs;
    SELECT COUNT(*) INTO resolved FROM swi74_resolved;
    IF expected <> resolved THEN
        RAISE EXCEPTION 'SWI-74 manual dedup: % pairs declared, % resolved (some losers/winners not active)', expected, resolved;
    END IF;
END $$;

-- Repoint articles + narrative_updates from loser to winner.
UPDATE articles a
SET narrative_id = r.winner_id
FROM swi74_resolved r
WHERE a.narrative_id = r.loser_id;

-- narrative_updates has a unique (narrative_id, article_id) constraint.
-- Delete loser-side updates that would collide with an existing winner-side
-- row, then repoint the rest.
DELETE FROM narrative_updates u
USING swi74_resolved r
WHERE u.narrative_id = r.loser_id
  AND EXISTS (
      SELECT 1 FROM narrative_updates u2
      WHERE u2.narrative_id = r.winner_id
        AND u2.article_id   = u.article_id
  );

UPDATE narrative_updates u
SET narrative_id = r.winner_id
FROM swi74_resolved r
WHERE u.narrative_id = r.loser_id;

-- Mark losers stale and link merged_into.
UPDATE narratives n
SET status       = 'stale',
    maturity     = 'stale',
    merged_into  = r.winner_id,
    summary      = COALESCE(n.summary, '')
                 || E'\n\n[SWI-74 manual dedup 2026-05-01: merged into '
                 || r.winner_key || ']',
    updated_at   = NOW()
FROM swi74_resolved r
WHERE n.id = r.loser_id;

-- Refresh winner aggregates from the now-broader article set.
UPDATE narratives w
SET article_count = sub.cnt,
    last_seen     = sub.last_seen,
    updated_at    = NOW()
FROM (
    SELECT a.narrative_id, COUNT(*) AS cnt, MAX(a.published_at::date) AS last_seen
    FROM articles a
    WHERE a.narrative_id IN (SELECT winner_id FROM swi74_resolved)
    GROUP BY a.narrative_id
) sub
WHERE w.id = sub.narrative_id;

INSERT INTO schema_migrations (version)
VALUES ('338_swi74_manual_dedup')
ON CONFLICT DO NOTHING;

COMMIT;
