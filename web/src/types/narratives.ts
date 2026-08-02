export type NarrativeType =
  | 'earnings'
  | 'regulatory'
  | 'macro'
  | 'corporate'
  | 'sector'
  | 'geopolitical'
  | 'general'

export type NarrativeStatus = 'active' | 'stale' | 'merged' | 'resolved'

export type SentimentShift = 'strengthens' | 'weakens' | 'neutral'

export type NarrativeMomentum = 'Building' | 'Steady' | 'Fading'

export type NarrativeMaturity = 'emerging' | 'developing' | 'confirmed' | 'mature' | 'fading' | 'stale'

export interface Narrative {
  id: string
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
  summary: string | null
  trading_implication: string | null
  status: NarrativeStatus
  maturity: NarrativeMaturity
  related_catalysts: string[] | null
  created_at: string
  updated_at: string
  updates?: NarrativeUpdate[]
}

export interface NarrativeUpdate {
  id: number
  article_id: string
  update_date: string
  headline: string
  sentiment_shift: SentimentShift | null
}
