import type { DipBuyMetadata } from './index'

// ── Enums (must match PostgreSQL exactly) ────────────────────────────────────

export type MarketRegime = 'RISK_ON' | 'RISK_OFF' | 'NEUTRAL'
export type GlobalRiskRegime = 'CALM' | 'CAUTIOUS' | 'ELEVATED' | 'CRISIS'
export type TradingMode = 'NORMAL' | 'LOW_CASH' | 'REALLOCATION'
export type RecAction = 'BUY' | 'SELL' | 'HOLD' | 'WATCH' | 'WAIT' | 'SKIP' | 'AVOID' | 'LIMIT_BUY' | 'EXIT' | 'TRIM' | 'ADD'
export type EvalStatus = 'WIN' | 'LOSS' | 'PENDING' | 'MISSED' | 'HOLD' | 'WATCH' | 'WAIT' | 'EXIT' | 'MISS'
export type FlowSignal = 'RISK_ON' | 'RISK_OFF' | 'NEUTRAL'
export type FlowPattern = 'Accumulation' | 'Distribution' | 'Neutral'
export type DxySignal = 'WEAK' | 'NEUTRAL' | 'STRONG'
export type VixSignal = 'LOW' | 'MODERATE' | 'HIGH' | 'EXTREME'
export type UsdVndSignal = 'STABLE' | 'PRESSURE' | 'FLIGHT'

// ── Geopolitical Shock ───────────────────────────────────────────────────────

export type ShockPhase = 'immediate_shock' | 'sustained_pressure' | 'resolution_or_escalation'

export interface GeopoliticalShockData {
  phase_name: ShockPhase
  catalyst_event: string
  behavior: string
  impact: string
  affected_tickers: string[]
  notes: string
  catalyst_key: string
  days_active?: number
  phase_stale?: boolean
}

// ── Daily Intel (combined response) ──────────────────────────────────────────

export interface DailyIntel {
  scan_date: string
  regime: RegimeData | null
  macro: MacroData | null
  foreign_flow: ForeignFlowData | null
  rotation: RotationData | null
  geopolitical_shock: GeopoliticalShockData | null
  articles: ArticleSummary[]
}

export interface RegimeData {
  regime: MarketRegime
  regime_confidence: number | null
  vn_index_value: number | null
  vn_index_change_pct: number | null
  key_signal: string | null
  recommendation: string | null
}

export interface MacroData {
  dxy_value: number | null
  dxy_change_pct: number | null
  dxy_signal: DxySignal | null
  vix_value: number | null
  vix_change_pct: number | null
  vix_signal: VixSignal | null
  usd_vnd_rate: number | null
  usd_vnd_signal: UsdVndSignal | null
  global_risk_regime: GlobalRiskRegime
  interpretation: string | null
}

export interface ForeignFlowData {
  net_value_billion: number | null
  buy_value_billion: number | null
  sell_value_billion: number | null
  signal: FlowSignal | null
  pattern: FlowPattern | null
  interpretation: string | null
  top_bought: FlowDetail[]
  top_sold: FlowDetail[]
  holding_details: FlowHoldingDetail[]
}

export interface FlowDetail {
  ticker: string
  value_billion: number
  rank: number
}

export interface FlowHoldingDetail {
  ticker: string
  buy_value_billion: number | null
  sell_value_billion: number | null
  net_value_billion: number | null
  ownership_pct: number | null
  remaining_room: number | null
}

export interface RotationData {
  rotation_signal: string | null
  reasoning: string | null
  hot_sectors: SectorDetail[]
  cold_sectors: SectorDetail[]
}

export interface SectorDetail {
  sector_name: string
  return_pct: number | null
}

export interface ArticleSummary {
  title: string
  url: string
  domain: string | null
  summary: string | null
  sentiment_score: number | null
  affected_tickers: string[]
}

// ── Recommendations ──────────────────────────────────────────────────────────

export interface RecommendationsData {
  record_date: string
  total_recs: number | null
  entry_hit_rate: number | null
  win_rate: number | null
  best_call: string | null
  worst_call: string | null
  key_insight: string | null
  trading_mode: TradingMode | null
  recommendations: Recommendation[]
}

export interface RecAlert {
  id: string
  status: 'active' | 'triggered' | 'expired' | 'cancelled'
  condition_type: string
  condition_value: number | null
  triggered_value: number | null
  triggered_at: string | null
  priority: 'high' | 'normal' | 'low'
  source: string
  alert_metadata: DipBuyMetadata | null
}

export interface Recommendation {
  ticker: string
  action: RecAction
  entry_price_vnd: number | null
  stop_price_vnd: number | null
  target_price_vnd: number | null
  size_shares: number | null
  rationale: string | null
  section: string | null
  strategy: string | null
  strategy_confidence: number | null
  risk_reward: number | null
  conservative_target_vnd: number | null
  aggressive_target_vnd: number | null
  conservative_rr: number | null
  aggressive_rr: number | null
  source: string | null
  sim_ev: number | null
  counter_thesis: string | null
  verdict: string | null
  evaluation: Evaluation | null
  alerts: RecAlert[]
}

export interface Evaluation {
  entry_hit: boolean
  stop_hit: boolean
  target_hit: boolean
  status: EvalStatus | null
  pnl_percent: number | null
  eod_price_vnd: number | null
  won: boolean | null
}

// ── Midday Check ─────────────────────────────────────────────────────────────

export interface AfternoonAction {
  ticker: string | null
  action: string
  confidence: string
  reason: string
}

export interface MiddayCheckData {
  trading_mode: TradingMode
  morning_reflection: string | null
  /** Server-rendered prose derived from afternoon_plan_raw (migration 316). */
  afternoon_plan: string | null
  /** Structured form (list[AfternoonAction]) for future readers. */
  afternoon_plan_raw: AfternoonAction[]
  capital_note: string | null
  entries_hit: MiddayEntry[]
  big_movers: MiddayMover[]
  position_alerts: MiddayAlert[]
  morning_position_alerts: MorningPositionAlert[]
  recommendation_overrides: RecommendationOverride[]
}

export interface MorningPositionAlert {
  ticker: string
  action: string
  urgency: string
  reason: string | null
  target_price: number | null
  stop_price: number | null
  consensus: string | null
  dissenting_views: string[]
  entry_price: number | null
  pct_from_entry: number | null
  weight_pct: number | null
  volume_signal: string | null
}

export interface RecommendationOverride {
  ticker: string
  morning_action: string
  midday_status: 'CONFIRM' | 'ADJUST' | 'CANCEL'
  reason: string
  revised_entry: number | null
  revised_stop: number | null
  revised_target: number | null
}

export interface MiddayEntry {
  ticker: string
  recommended_entry_vnd: number | null
  actual_low_vnd: number | null
  current_price_vnd: number | null
  status: string | null
}

export interface MiddayMover {
  ticker: string
  open_price_vnd: number | null
  current_price_vnd: number | null
  change_pct: number
  direction: string | null
}

export interface MiddayAlert {
  ticker: string
  current_price_vnd: number | null
  level_vnd: number | null
  level_type: string | null
  distance_pct: number | null
  urgency: string | null
}

// ── Learnings ────────────────────────────────────────────────────────────────

export interface LearningsData {
  summary: LearningSummary | null
  winning_patterns: LearningPattern[]
  losing_patterns: LearningPattern[]
  sector_insights: SectorInsight[]
  ticker_insights: TickerInsight[]
}

export interface LearningSummary {
  total_days: number
  total_recs: number
  overall_entry_hit_rate: number | null
  overall_win_rate: number | null
  avg_pnl_percent: number | null
}

export interface LearningPattern {
  description: string
  win_rate: number | null
  loss_rate: number | null
  sample_size: number | null
  actionable_rule: string | null
  avoid_rule: string | null
  dominant_error: 'ANALYSIS_ERROR' | 'EXECUTION_ERROR' | 'CALIBRATION_ERROR' | 'VARIANCE' | null
}

export interface SectorInsight {
  sector_name: string
  bias: string | null
  win_rate: number | null
}

export interface TickerInsight {
  ticker: string
  recent_accuracy: number | null
}
