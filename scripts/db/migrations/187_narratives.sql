-- Narrative Intelligence: track developing news stories across days.
-- Articles cluster into narrative threads via embedding similarity.
-- Conviction scores decay exponentially based on narrative type.

-- ── Main table: narrative threads ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS narratives (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    narrative_key VARCHAR(100) NOT NULL UNIQUE,
    theme TEXT NOT NULL,
    narrative_type VARCHAR(30) NOT NULL,
    affected_tickers TEXT[] DEFAULT '{}',
    affected_sectors TEXT[] DEFAULT '{}',

    article_count INTEGER DEFAULT 1,
    source_count INTEGER DEFAULT 1,
    avg_sentiment FLOAT DEFAULT 0.0,

    first_seen DATE NOT NULL,
    last_seen DATE NOT NULL,

    conviction_score FLOAT DEFAULT 0.5,
    half_life_days INTEGER DEFAULT 3,

    summary TEXT,
    trading_implication TEXT,

    centroid_embedding vector(384),

    status VARCHAR(20) DEFAULT 'active',
    merged_into UUID REFERENCES narratives(id),
    related_catalysts TEXT[],

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Child table: per-article updates linked to a narrative ───────────────────
CREATE TABLE IF NOT EXISTS narrative_updates (
    id SERIAL PRIMARY KEY,
    narrative_id UUID NOT NULL REFERENCES narratives(id),
    article_id UUID NOT NULL,
    update_date DATE NOT NULL,
    headline TEXT NOT NULL,
    sentiment_shift VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Extend articles table ────────────────────────────────────────────────────
ALTER TABLE articles ADD COLUMN IF NOT EXISTS
    content_embedding vector(384);
ALTER TABLE articles ADD COLUMN IF NOT EXISTS
    narrative_id UUID REFERENCES narratives(id);

-- ── Indexes ──────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_narratives_status
    ON narratives(status);
CREATE INDEX IF NOT EXISTS idx_narratives_tickers
    ON narratives USING GIN(affected_tickers);
CREATE INDEX IF NOT EXISTS idx_narratives_conviction
    ON narratives(conviction_score DESC) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_narratives_centroid
    ON narratives USING hnsw(centroid_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_articles_embedding
    ON articles USING hnsw(content_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_narrative_updates_narrative
    ON narrative_updates(narrative_id);
CREATE INDEX IF NOT EXISTS idx_articles_narrative
    ON articles(narrative_id) WHERE narrative_id IS NOT NULL;
