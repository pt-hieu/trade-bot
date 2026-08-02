import { createServerFn } from '@tanstack/react-start'
import { getSql } from '../db'
import type { NarrativeType, NarrativeStatus, NarrativeMaturity } from '../../types/narratives'

type GetNarrativesInput = {
  status?: string | null
  type?: string | null
  ticker?: string | null
}

export const getNarratives = createServerFn({ method: 'GET' })
  .inputValidator((data: GetNarrativesInput) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const { status, type, ticker } = data

    // Neon tagged templates don't support dynamic WHERE — use separate queries
    if (status && type && ticker) {
      return sql`
        SELECT n.*, COALESCE(json_agg(json_build_object(
          'id', nu.id, 'article_id', nu.article_id, 'update_date', nu.update_date,
          'headline', nu.headline, 'sentiment_shift', nu.sentiment_shift
        ) ORDER BY nu.update_date DESC) FILTER (WHERE nu.id IS NOT NULL), '[]') AS updates
        FROM narratives n LEFT JOIN narrative_updates nu ON nu.narrative_id = n.id
        WHERE n.pipeline_version = 'v2' AND n.status = ${status} AND n.narrative_type = ${type} AND ${ticker} = ANY(n.affected_tickers)
        GROUP BY n.id ORDER BY n.conviction_score DESC, n.last_seen DESC`
    } else if (status && type) {
      return sql`
        SELECT n.*, COALESCE(json_agg(json_build_object(
          'id', nu.id, 'article_id', nu.article_id, 'update_date', nu.update_date,
          'headline', nu.headline, 'sentiment_shift', nu.sentiment_shift
        ) ORDER BY nu.update_date DESC) FILTER (WHERE nu.id IS NOT NULL), '[]') AS updates
        FROM narratives n LEFT JOIN narrative_updates nu ON nu.narrative_id = n.id
        WHERE n.pipeline_version = 'v2' AND n.status = ${status} AND n.narrative_type = ${type}
        GROUP BY n.id ORDER BY n.conviction_score DESC, n.last_seen DESC`
    } else if (status && ticker) {
      return sql`
        SELECT n.*, COALESCE(json_agg(json_build_object(
          'id', nu.id, 'article_id', nu.article_id, 'update_date', nu.update_date,
          'headline', nu.headline, 'sentiment_shift', nu.sentiment_shift
        ) ORDER BY nu.update_date DESC) FILTER (WHERE nu.id IS NOT NULL), '[]') AS updates
        FROM narratives n LEFT JOIN narrative_updates nu ON nu.narrative_id = n.id
        WHERE n.pipeline_version = 'v2' AND n.status = ${status} AND ${ticker} = ANY(n.affected_tickers)
        GROUP BY n.id ORDER BY n.conviction_score DESC, n.last_seen DESC`
    } else if (type && ticker) {
      return sql`
        SELECT n.*, COALESCE(json_agg(json_build_object(
          'id', nu.id, 'article_id', nu.article_id, 'update_date', nu.update_date,
          'headline', nu.headline, 'sentiment_shift', nu.sentiment_shift
        ) ORDER BY nu.update_date DESC) FILTER (WHERE nu.id IS NOT NULL), '[]') AS updates
        FROM narratives n LEFT JOIN narrative_updates nu ON nu.narrative_id = n.id
        WHERE n.pipeline_version = 'v2' AND n.narrative_type = ${type} AND ${ticker} = ANY(n.affected_tickers)
        GROUP BY n.id ORDER BY n.conviction_score DESC, n.last_seen DESC`
    } else if (status) {
      return sql`
        SELECT n.*, COALESCE(json_agg(json_build_object(
          'id', nu.id, 'article_id', nu.article_id, 'update_date', nu.update_date,
          'headline', nu.headline, 'sentiment_shift', nu.sentiment_shift
        ) ORDER BY nu.update_date DESC) FILTER (WHERE nu.id IS NOT NULL), '[]') AS updates
        FROM narratives n LEFT JOIN narrative_updates nu ON nu.narrative_id = n.id
        WHERE n.pipeline_version = 'v2' AND n.status = ${status}
        GROUP BY n.id ORDER BY n.conviction_score DESC, n.last_seen DESC`
    } else if (type) {
      return sql`
        SELECT n.*, COALESCE(json_agg(json_build_object(
          'id', nu.id, 'article_id', nu.article_id, 'update_date', nu.update_date,
          'headline', nu.headline, 'sentiment_shift', nu.sentiment_shift
        ) ORDER BY nu.update_date DESC) FILTER (WHERE nu.id IS NOT NULL), '[]') AS updates
        FROM narratives n LEFT JOIN narrative_updates nu ON nu.narrative_id = n.id
        WHERE n.pipeline_version = 'v2' AND n.narrative_type = ${type}
        GROUP BY n.id ORDER BY n.conviction_score DESC, n.last_seen DESC`
    } else if (ticker) {
      return sql`
        SELECT n.*, COALESCE(json_agg(json_build_object(
          'id', nu.id, 'article_id', nu.article_id, 'update_date', nu.update_date,
          'headline', nu.headline, 'sentiment_shift', nu.sentiment_shift
        ) ORDER BY nu.update_date DESC) FILTER (WHERE nu.id IS NOT NULL), '[]') AS updates
        FROM narratives n LEFT JOIN narrative_updates nu ON nu.narrative_id = n.id
        WHERE n.pipeline_version = 'v2' AND ${ticker} = ANY(n.affected_tickers)
        GROUP BY n.id ORDER BY n.conviction_score DESC, n.last_seen DESC`
    } else {
      return sql`
        SELECT n.*, COALESCE(json_agg(json_build_object(
          'id', nu.id, 'article_id', nu.article_id, 'update_date', nu.update_date,
          'headline', nu.headline, 'sentiment_shift', nu.sentiment_shift
        ) ORDER BY nu.update_date DESC) FILTER (WHERE nu.id IS NOT NULL), '[]') AS updates
        FROM narratives n LEFT JOIN narrative_updates nu ON nu.narrative_id = n.id
        WHERE n.pipeline_version = 'v2'
        GROUP BY n.id ORDER BY n.conviction_score DESC, n.last_seen DESC`
    }
  })

export interface NarrativeInput {
  narrative_key: string
  theme: string
  narrative_type: NarrativeType
  affected_tickers: string[]
  affected_sectors: string[]
  article_count: number
  source_count: number
  avg_sentiment: number
  first_seen: string
  last_seen: string
  conviction_score: number
  half_life_days: number
  summary?: string | null
  trading_implication?: string | null
  status?: NarrativeStatus
  maturity?: NarrativeMaturity
  related_catalysts?: string[] | null
}

export const createNarrative = createServerFn({ method: 'POST' })
  .inputValidator((data: NarrativeInput) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const rows = await sql`
      INSERT INTO narratives (
        narrative_key, theme, narrative_type,
        affected_tickers, affected_sectors,
        article_count, source_count, avg_sentiment,
        first_seen, last_seen, conviction_score, half_life_days,
        summary, trading_implication, status, related_catalysts
      ) VALUES (
        ${data.narrative_key},
        ${data.theme},
        ${data.narrative_type},
        ${data.affected_tickers},
        ${data.affected_sectors},
        ${data.article_count},
        ${data.source_count},
        ${data.avg_sentiment},
        ${data.first_seen},
        ${data.last_seen},
        ${data.conviction_score},
        ${data.half_life_days},
        ${data.summary ?? null},
        ${data.trading_implication ?? null},
        ${data.status ?? 'active'},
        ${data.related_catalysts ?? null}
      )
      RETURNING *
    `
    return rows[0]
  })

type UpdateNarrativeInput = { id: string } & Partial<NarrativeInput>

export const updateNarrative = createServerFn({ method: 'POST' })
  .inputValidator((data: UpdateNarrativeInput) => data)
  .handler(async ({ data }) => {
    const { id, ...input } = data
    const sql = getSql()
    const rows = await sql`
      UPDATE narratives SET
        narrative_key = COALESCE(${input.narrative_key ?? null}, narrative_key),
        theme = COALESCE(${input.theme ?? null}, theme),
        narrative_type = COALESCE(${input.narrative_type ?? null}, narrative_type),
        affected_tickers = COALESCE(${input.affected_tickers ?? null}, affected_tickers),
        affected_sectors = COALESCE(${input.affected_sectors ?? null}, affected_sectors),
        article_count = COALESCE(${input.article_count ?? null}, article_count),
        source_count = COALESCE(${input.source_count ?? null}, source_count),
        avg_sentiment = COALESCE(${input.avg_sentiment ?? null}, avg_sentiment),
        first_seen = COALESCE(${input.first_seen ?? null}, first_seen),
        last_seen = COALESCE(${input.last_seen ?? null}, last_seen),
        conviction_score = COALESCE(${input.conviction_score ?? null}, conviction_score),
        half_life_days = COALESCE(${input.half_life_days ?? null}, half_life_days),
        summary = ${input.summary ?? null},
        trading_implication = ${input.trading_implication ?? null},
        status = COALESCE(${input.status ?? null}, status),
        related_catalysts = ${input.related_catalysts ?? null},
        updated_at = NOW()
      WHERE id = ${id}
      RETURNING *
    `
    if (rows.length === 0) {
      throw new Error('Narrative not found')
    }
    return rows[0]
  })
