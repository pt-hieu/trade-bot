// DB enum values — match PostgreSQL CHECK constraints exactly
export type CatalystImpact = 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL'
export type CatalystConfidence = 'HIGH' | 'MEDIUM' | 'LOW'
export type CatalystStatus = 'active' | 'monitoring' | 'imminent' | 'resolved' | 'expired'

export type CapitalEventType =
  | 'capital_increase'
  | 'ipo'
  | 'stock_split'
  | 'ma'
  | 'buyback'
  | 'dividend'

export type CapitalEventImpact =
  | 'POSITIVE'
  | 'NEGATIVE_SHORT_TERM'
  | 'NEGATIVE_LONG_TERM'
  | 'WATCH'

export type CapitalEventStatus = 'pending' | 'completed'

export interface Catalyst {
  id: number
  catalyst_key: string
  event: string
  expected: string
  affected_tickers: string[]
  impact: CatalystImpact
  confidence: CatalystConfidence
  notes: string | null
  source: string | null
  phases: Record<string, { period: string; impact: string; behavior: string }> | null
  status: CatalystStatus
  outcome: string | null
  actual_date: string | null
  expected_date: string | null
  last_confirmed_at: string | null
  added_date: string
  last_updated: string | null
  created_at: string
  updated_at: string
}

export interface CatalystInput {
  catalyst_key: string
  event: string
  expected: string
  affected_tickers: string[]
  impact: CatalystImpact
  confidence: CatalystConfidence
  notes?: string | null
  source?: string | null
  status?: CatalystStatus
  outcome?: string | null
  actual_date?: string | null
  expected_date?: string | null
  last_confirmed_at?: string | null
}

export interface CapitalEvent {
  id: number
  event_key: string
  ticker: string
  event_type: CapitalEventType
  description: string
  amount: string | null
  expected_date: string
  dilution_pct: number | null
  impact: CapitalEventImpact
  source: string | null
  status: CapitalEventStatus
  added_date: string
  created_at: string
  updated_at: string
}

export interface CapitalEventInput {
  event_key: string
  ticker: string
  event_type: CapitalEventType
  description: string
  amount?: string | null
  expected_date: string
  dilution_pct?: number | null
  impact: CapitalEventImpact
  source?: string | null
  status?: CapitalEventStatus
}
