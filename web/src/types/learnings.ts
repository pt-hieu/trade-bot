import type { LearningPattern, SectorInsight, TickerInsight } from './intel'

export interface EnrichedLearningSummary {
  total_days: number
  total_recs: number
  overall_entry_hit_rate: number | null
  overall_win_rate: number | null
  avg_pnl_percent: number | null
  last_updated: string | null
}

export interface StrategyInsight {
  strategy: string
  win_rate: number | null
  sample_size: number | null
}

export interface TradingRule {
  rule_name: string
  description: string
  action: string
  confidence: number | null
  sample_size: number | null
  expires_at: string | null
}

export interface CalibrationInsights {
  avg_entry_gap_pct: number | null
  pct_entries_unreachable: number | null
  avg_stop_vs_atr: number | null
  pct_stops_too_tight: number | null
  avg_predicted_rr: number | null
  avg_actual_rr: number | null
  target_hit_rate: number | null
  sample_size: number | null
}

export interface MiddayPatterns {
  days_with_midday: number | null
  adjustment_win_rate: number | null
  when_helpful: string[]
  when_harmful: string[]
  average_improvement: number | null
}

export interface TradingModePatterns {
  mode_compliance_rate: number | null
  mode_violations: string[]
  mode_appropriate_win_rate: number | null
}

export interface RotationSectorScore {
  sector_name: string
  as_hot_accuracy: number | null
  as_cold_accuracy: number | null
}

export interface RotationPatterns {
  total_days: number | null
  overall_accuracy: number | null
  hot_hit_rate: number | null
  cold_hit_rate: number | null
  avg_hot_vs_market: number | null
  avg_cold_vs_market: number | null
  sector_scores: RotationSectorScore[]
}

export interface MacroRegimeAccuracy {
  regime: 'CALM' | 'CAUTIOUS' | 'ELEVATED' | 'CRISIS' | string
  days_count: number | null
  correct_count: number | null
  avg_vn_change: number | null
}

export interface MacroPatterns {
  total_days: number | null
  overall_accuracy: number | null
  false_alarms: number | null
  missed_drops: number | null
  missed_opportunities: number | null
  regime_accuracy: MacroRegimeAccuracy[]
}

export type HealthStatus = 'green' | 'amber' | 'red'

export type SubsystemName =
  | 'win-rate'
  | 'entry-hit'
  | 'avg-pnl'
  | 'calibration'
  | 'macro'
  | 'rotation'
  | 'strategy'
  | 'trading-mode'

export interface SubsystemHealth {
  name: SubsystemName
  status: HealthStatus
  label: string
  value: string
  insufficientData?: boolean
}

export interface HealthVerdict {
  overallStatus: HealthStatus
  summary: string
  subsystems: SubsystemHealth[]
  failures: SubsystemHealth[]
  unmeasurable: SubsystemHealth[]
  attentionCount: number
}

export interface WeeklyTrend {
  week: string
  winRate: number | null
  entryHit: number | null
  avgPnl: number | null
  totalRecs: number
}

export interface EnrichedLearningsData {
  summary: EnrichedLearningSummary | null
  winning_patterns: LearningPattern[]
  losing_patterns: LearningPattern[]
  sector_insights: SectorInsight[]
  ticker_insights: TickerInsight[]
  calibration: CalibrationInsights | null
  midday: MiddayPatterns | null
  trading_mode: TradingModePatterns | null
  rotation: RotationPatterns | null
  macro: MacroPatterns | null
  strategy_insights: StrategyInsight[]
  trading_rules: TradingRule[]
  trends: WeeklyTrend[]
}
