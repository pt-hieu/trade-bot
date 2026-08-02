-- Migration 007: Add pgvector for similarity search
-- Enables episodic + semantic memory pattern for trading agents
--
-- Prerequisites: Neon PostgreSQL with pgvector extension available

-- Enable pgvector extension (Neon supports this natively)
CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding column to daily_records for episodic memory
-- 384 dimensions for all-MiniLM-L6-v2 model
ALTER TABLE daily_records
ADD COLUMN IF NOT EXISTS context_embedding vector(384);

-- Add embedding column to learning_patterns for pattern similarity
ALTER TABLE learning_patterns
ADD COLUMN IF NOT EXISTS pattern_embedding vector(384);

-- Create HNSW indexes for similarity search
-- HNSW is recommended by Neon: better recall, works on empty tables
-- Using cosine distance (vector_cosine_ops) for text embeddings

-- Index for finding similar trading days
CREATE INDEX IF NOT EXISTS idx_daily_embedding ON daily_records
USING hnsw (context_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Index for finding similar patterns
CREATE INDEX IF NOT EXISTS idx_pattern_embedding ON learning_patterns
USING hnsw (pattern_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Semantic trading rules table
-- Extracted from winning/losing patterns with structured conditions
CREATE TABLE IF NOT EXISTS trading_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Rule definition
    rule_name VARCHAR(100) NOT NULL UNIQUE,
    rule_type VARCHAR(20) CHECK (rule_type IN ('entry', 'exit', 'avoid', 'size')),
    description TEXT NOT NULL,

    -- Conditions (when to apply)
    condition_regime market_regime[],     -- [RISK_ON, NEUTRAL]
    condition_sectors VARCHAR(50)[],       -- [banking, tech]
    condition_rsi_range INT4RANGE,         -- [25, 40)
    condition_macro VARCHAR(20)[],         -- [CALM, CAUTIOUS]

    -- Action
    action TEXT NOT NULL,                  -- "BUY at support"
    confidence DECIMAL(4, 2) NOT NULL,     -- 0.75

    -- Source tracking
    derived_from_pattern_id UUID REFERENCES learning_patterns(id),
    sample_size INTEGER,
    last_validated DATE,

    -- Embedding for similarity search
    rule_embedding vector(384),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for trading_rules
CREATE INDEX IF NOT EXISTS idx_rules_type ON trading_rules(rule_type);
CREATE INDEX IF NOT EXISTS idx_rules_confidence ON trading_rules(confidence DESC);

-- HNSW index for rule similarity search
CREATE INDEX IF NOT EXISTS idx_rules_embedding ON trading_rules
USING hnsw (rule_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
