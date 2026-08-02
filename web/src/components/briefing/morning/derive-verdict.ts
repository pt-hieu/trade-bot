import type { Recommendation, RecommendationsData, RecAction } from '../../../types/intel'

// ── Types ───────────────────────────────────────────────────────────────────

export type VerdictTone = 'defensive' | 'offensive' | 'steady'

export interface ActionItem {
  ticker: string
  action: RecAction
  entryPriceVnd: number | null
  stopPriceVnd: number | null
  targetPriceVnd: number | null
  riskReward: number | null
  section: string | null
}

export interface VerdictData {
  tone: VerdictTone
  summary: string
  tradingMode: RecommendationsData['trading_mode']
  actionItems: ActionItem[]
  holdCount: number
  watchCount: number
}

export interface ProximityRec {
  rec: Recommendation
  /** Signed: positive = above entry (needs pullback), negative = below entry (in zone) */
  distancePct: number
}

// ── Verdict derivation ──────────────────────────────────────────────────────

const ACTIONABLE: Set<RecAction> = new Set(['BUY', 'SELL', 'ADD', 'LIMIT_BUY', 'EXIT', 'TRIM'])
const DEFENSIVE: Set<RecAction> = new Set(['EXIT', 'TRIM', 'SELL'])
const OFFENSIVE: Set<RecAction> = new Set(['BUY', 'ADD', 'LIMIT_BUY'])

export function deriveVerdict(recs: RecommendationsData | null): VerdictData {
  const allRecs = recs?.recommendations ?? []

  const actionItems: ActionItem[] = allRecs
    .filter((rec) => ACTIONABLE.has(rec.action))
    .map((rec) => ({
      ticker: rec.ticker,
      action: rec.action,
      entryPriceVnd: rec.entry_price_vnd,
      stopPriceVnd: rec.stop_price_vnd,
      targetPriceVnd: rec.target_price_vnd,
      riskReward: rec.risk_reward,
      section: rec.section,
    }))
    // Defense first, then offense
    .sort((itemA, itemB) => {
      const aDefense = DEFENSIVE.has(itemA.action) ? 0 : 1
      const bDefense = DEFENSIVE.has(itemB.action) ? 0 : 1
      return aDefense - bDefense
    })

  const holdCount = allRecs.filter((rec) => rec.action === 'HOLD' && rec.section === 'MY_HOLDINGS').length
  const watchCount = allRecs.filter((rec) => rec.action === 'WATCH' || rec.action === 'WAIT').length

  // Determine tone
  const hasDefensive = actionItems.some((item) => DEFENSIVE.has(item.action))
  const hasOffensive = actionItems.some((item) => OFFENSIVE.has(item.action))
  const tone: VerdictTone = hasDefensive ? 'defensive' : hasOffensive ? 'offensive' : 'steady'

  // Summary: prefer key_insight from pipeline, fallback to generated
  const summary = recs?.key_insight
    ?? (actionItems.length > 0
      ? `${actionItems.length} action${actionItems.length !== 1 ? 's' : ''} today`
      : 'Hold steady — no new actions today')

  return {
    tone,
    summary,
    tradingMode: recs?.trading_mode ?? null,
    actionItems,
    holdCount,
    watchCount,
  }
}

// ── Proximity helpers ───────────────────────────────────────────────────────

export function computeProximity(recs: Recommendation[]): ProximityRec[] {
  const withDistance: ProximityRec[] = []
  const withoutDistance: ProximityRec[] = []

  for (const rec of recs) {
    const entry = rec.entry_price_vnd
    const eod = rec.evaluation?.eod_price_vnd
    if (entry != null && eod != null && entry > 0) {
      const distancePct = ((Number(eod) - Number(entry)) / Number(entry)) * 100
      withDistance.push({ rec, distancePct })
    } else {
      withoutDistance.push({ rec, distancePct: Infinity })
    }
  }

  // Sort by absolute distance ascending (nearest first)
  withDistance.sort((itemA, itemB) => Math.abs(itemA.distancePct) - Math.abs(itemB.distancePct))

  return [...withDistance, ...withoutDistance]
}

export function findClosestMiss(longTermRecs: Recommendation[]): ProximityRec | null {
  const sorted = computeProximity(longTermRecs)
  // Return closest rec that has computable distance
  return sorted.find((item) => item.distancePct !== Infinity) ?? null
}
