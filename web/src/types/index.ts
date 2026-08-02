export * from './chat'

export type StockType =
  | 'Private' | 'State' | 'Industrial' | 'Vingroup' | 'Retail'
  | 'Securities' | 'Conglomerate' | 'Energy' | 'Commodities'
  | 'Aviation' | 'Insurance' | 'Beverages' | 'Dairy' | 'Logistics' | 'Steel'

export type ConvictionLevel = 'High' | 'Medium-High' | 'Medium' | 'Medium-Low' | 'Low'

export interface SwingWatchlistItem {
  id: string
  ticker: string
  sector_name: string
  stock_type: StockType | null
  rsi: number | null
  notes: string | null
  is_pinned: boolean
  pin_reason: string | null
  created_at: string
  updated_at: string
}

export interface LongtermWatchlistItem {
  id: string
  ticker: string
  sector_name: string
  entry_zone_vnd: number
  conviction: ConvictionLevel
  pe_ratio: number | null
  roe: number | null
  dividend_yield: number | null
  tier: number | null
  notes: string | null
  created_at: string
  updated_at: string
  entry_zone_method: string | null
  conviction_score: number | null
  conviction_method: string | null
  review_flags: string[]
  last_reviewed_at: string | null
}

export type ResearchSectionKey =
  | 'overview' | 'financials' | 'moat' | 'management'
  | 'growth' | 'risks' | 'valuation' | 'thesis'

export interface CompanyResearch {
  ticker: string
  sections: Partial<Record<ResearchSectionKey, string>>
  research_date: string
  auto_generated: boolean
  version: number
  updated_at: string
}

export interface Trade {
  id: string
  ticker: string
  plan_type: 'SWING' | 'LONGTERM'
  strategy: 'Bounce' | 'Trend' | 'Breakout' | 'Divergence' | 'Mean Reversion' | 'Momentum' | 'Pullback' | null
  entry_date: string
  entry_price_vnd: number
  exit_date: string | null
  exit_price_vnd: number | null
  shares: number
  buy_total_vnd: number
  pl_gross_vnd: number | null
  pl_net_vnd: number | null
  pl_pct: number | null
  days_held: number | null
  result: 'WIN' | 'LOSS' | null
  status: 'OPEN' | 'CLOSED'
}

export interface PortfolioHolding {
  ticker: string
  holding_type: 'Stock' | 'ETF' | 'Cash'
  shares: number
  avg_cost_vnd: number
  current_price_vnd: number | null
  cost_basis_vnd: number
  market_value_vnd: number
  pl_vnd: number
  pl_pct: number
  sector_name: string | null
}

export interface PortfolioSummary {
  marketValue: number
  costBasis: number
  unrealizedPl: number
  unrealizedPlPct: number
  unrealizedTrend: 'up' | 'down' | 'flat'
  realizedPl: number
  closedTradeCount: number
  totalReturn: number
  totalReturnPct: number
  alphaVsVnindex: number
  vnindexReturnPct: number
  cashAvailable: number
  cashDeployedPct: number
  positionCount: number
  lastUpdated: string | null
}

export interface EnhancedHolding {
  ticker: string
  sectorName: string | null
  shares: number
  avgCostVnd: number
  currentPriceVnd: number | null
  costBasisVnd: number
  marketValueVnd: number
  plVnd: number
  plPct: number
  strategy: string | null
  entryDate: string | null
  planType: string | null
  daysHeld: number | null
  systemAligned: boolean
  stopPriceVnd: number | null
  vsStopPct: number | null
  weightPct: number
}

export interface SectorConcentration {
  sectorName: string
  marketValueVnd: number
  weightPct: number
}

export interface PositionSizingViolation {
  ticker: string
  weightPct: number
  limitPct: number
}

export interface TickerContext {
  catalystCount: number
  narrativeCount: number
  capitalEventCount: number
  hasNegative: boolean
}

export interface PortfolioMetrics {
  sectors: SectorConcentration[]
  herfindahlIndex: number
  concentrationLabel: 'Diversified' | 'Moderate' | 'Concentrated'
  avgDaysHeld: number
  longestOpen: { ticker: string; days: number; entryDate: string } | null
  maxDrawdown: { ticker: string; plPct: number } | null
  systemAlignmentPct: number
  systemAlignedCount: number
  systemTotalCount: number
  portfolioHeatCount: number
  portfolioHeatTotal: number
  closedWins: number
  closedLosses: number
  closedWinRate: number
  avgWinPct: number
  avgLossPct: number
  positionViolations: PositionSizingViolation[]
  marketValue: number
  costBasis: number
}

export interface VnindexDataPoint {
  snapshotDate: string
  value: number
}

export interface TradeInput {
  ticker: string
  entry_date: string
  entry_price_vnd: number
  shares: number
  strategy: 'Bounce' | 'Trend' | 'Breakout' | 'Divergence' | 'Mean Reversion' | 'Momentum' | 'Pullback' | null
  plan_type: 'SWING' | 'LONGTERM'
  status: 'OPEN' | 'CLOSED'
  exit_date?: string | null
  exit_price_vnd?: number | null
  exit_shares?: number
}

export interface SwingMetrics {
  total_trades: number
  wins: number
  losses: number
  win_rate: number
  total_return_vnd: number
  avg_win_vnd: number | null
  avg_loss_vnd: number | null
  profit_factor: number | null
  expectancy_vnd: number | null
  avg_holding_days: number | null
  max_win_vnd: number | null
  max_loss_vnd: number | null
}

export interface Goal {
  id: string
  name: string
  target_vnd: number
  realized_vnd: number
  start_date: string
  deadline: string
  status: 'Active' | 'Achieved' | 'Failed' | 'Paused' | 'Tracking'
  goal_type: 'Monthly' | 'Quarterly' | 'Yearly' | 'Custom'
  notes: string | null
}

export interface StrategyMetrics {
  strategy: string
  trades: number
  wins: number
  losses: number
  win_rate: number
  profit_factor: number | null
  total_pl_vnd: number
}

export interface PortfolioSnapshot {
  snapshot_date: string
  invested_value_vnd: number
}

export interface TradeEvent {
  date: string
  ticker: string
  action: 'BUY' | 'SELL'
  shares: number
  plan_type: 'SWING' | 'LONGTERM'
}

export interface PortfolioHistoryResponse {
  snapshots: PortfolioSnapshot[]
  trades: TradeEvent[]
  vnindex: VnindexDataPoint[]
}

export interface DateHolding {
  ticker: string
  shares: number
  close_vnd: number
  market_value_vnd: number
  plan_type: 'SWING' | 'LONGTERM'
}

export interface GoalInput {
  name: string
  target_vnd: number
  realized_vnd?: number
  start_date: string
  deadline: string
  status: 'Active' | 'Achieved' | 'Failed' | 'Paused' | 'Tracking'
  goal_type: 'Monthly' | 'Quarterly' | 'Yearly' | 'Custom'
  notes?: string | null
}

export interface Sector {
  id: number
  name: string
  display_name: string
}

export interface WatchlistAddInput {
  ticker: string
  type: 'swing' | 'longterm'
  sector_name: string
  // Swing-specific
  stock_type?: StockType
  is_pinned?: boolean
  pin_reason?: string
  // Longterm-specific
  entry_zone_vnd?: number
  conviction?: ConvictionLevel
  tier?: number
  // Shared
  notes?: string
}

export interface WatchlistRemoveInput {
  ticker: string
  type: 'swing' | 'longterm'
}

export interface RiskMetrics {
  data_points: number
  minimum_required: number
  portfolio_beta: number | null
  sharpe_ratio: number | null
  sortino_ratio: number | null
  ticker_betas: Record<string, number>
  risk_free_rate: number
  message?: string
}

export interface WatchlistEditInput {
  ticker: string
  type: 'swing' | 'longterm'
  stock_type?: StockType
  is_pinned?: boolean
  pin_reason?: string | null
  conviction?: ConvictionLevel
  tier?: number
  entry_zone_vnd?: number
  notes?: string | null
}

export type AlertConditionType = 'price_below' | 'price_above' | 'rsi_below' | 'rsi_above' | 'volume_spike'
export type AlertAction = 'BUY' | 'TRIM' | 'EXIT' | 'ADD' | 'WATCH'

export interface DipBuyMetadata {
  setup_id: string
  tranche: number
  total_tranches: number
  setup_type: 'CAPITULATION' | 'EXHAUSTION' | 'ORDERLY_DECLINE'
  pct_of_size: number
  conviction: 'HIGH' | 'MEDIUM' | 'LOW'
}

export interface AlertCondition {
  id: string
  condition_type: AlertConditionType
  condition_value: number | null
  params: Record<string, unknown>
  sort_order: number
}

export interface Alert {
  id: string
  ticker: string
  conditions: AlertCondition[]
  condition_logic: 'ALL' | 'ANY'
  action_type: string
  source: string
  source_date: string
  rationale: string | null
  recommended_action: string | null
  entry_price: number | null
  stop_price: number | null
  target_price: number | null
  status: 'active' | 'triggered' | 'expired' | 'cancelled'
  priority: 'high' | 'normal' | 'low'
  triggered_at: string | null
  triggered_values: Record<string, number> | null
  expires_at: string | null
  alert_metadata: DipBuyMetadata | null
  created_at: string
  updated_at: string
}

export interface AlertConditionInput {
  type: AlertConditionType
  value: number
}

export interface AlertInput {
  ticker: string
  conditions: AlertConditionInput[]
  condition_logic?: 'ALL' | 'ANY'
  recommended_action: AlertAction | null
  priority: 'high' | 'normal' | 'low'
  rationale?: string | null
  entry_price?: number | null
  stop_price?: number | null
  target_price?: number | null
}

export interface TradingConfig {
  id: number
  // Core Risk
  min_cash_reserve: number
  max_risk_per_trade: number
  low_cash_threshold: number
  max_concurrent_positions: number
  transaction_cost_pct: number
  monthly_contribution: number
  // Concentration Limits
  concentration_exit_pct: number
  swing_trim_weight_pct: number
  swing_trim_gain_pct: number
  longterm_trim_weight_high_pct: number
  longterm_trim_weight_med_pct: number
  longterm_review_weight_pct: number
  sector_concentration_high_pct: number
  sector_concentration_med_pct: number
  // Trailing Stops
  breakeven_gain_pct: number
  half_trail_gain_pct: number
  tight_trail_gain_pct: number
  tight_current_floor_pct: number
  tight_gain_lock_pct: number
  longterm_catastrophic_pct: number
  // Win Rate Scale
  full_winrate_threshold: number
  reduced_winrate_threshold: number
  half_winrate_threshold: number
  minimal_scale_factor: number
  // Retro Constraints
  retro_severe_winrate: number
  retro_moderate_winrate: number
  retro_severe_max_entries: number
  retro_severe_min_rr: number
  retro_severe_scale: number
  retro_moderate_max_entries: number
  retro_moderate_min_rr: number
  // Metadata
  updated_at: string
}

export interface SectorAllocation {
  id: number
  sector_name: string
  target_pct: number
  updated_at: string
}

export * from './catalysts'
export * from './intel'
export * from './agents'
export * from './learnings'
export * from './narratives'
