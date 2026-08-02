// Unified watchlist: merge swing + longterm into readiness-tiered view.

import type { SwingWatchlistItem, LongtermWatchlistItem, ConvictionLevel } from '../types/index'
import { classifyRsi } from './rsi'
import { computeEntryProximity } from './watchlist-utils'
import type { EntryProximity } from './watchlist-utils'

// ─── Types ───────────────────────────────────────────────────────────────────

export type ReadinessTier = 'near_entry' | 'setting_up' | 'watching'
export type PlanType = 'swing' | 'longterm'

export interface UnifiedWatchlistItem {
  ticker: string
  sectorName: string
  plans: PlanType[]
  readiness: ReadinessTier
  currentPrice: number | null
  // Swing data
  rsi: number | null
  rsiZone: string | null
  rsiLabel: string | null
  rsiBadgeClass: string | null
  stockType: string | null
  isPinned: boolean
  pinReason: string | null
  swingNotes: string | null
  // Long-term data
  entryZoneVnd: number | null
  entryProximity: EntryProximity | null
  conviction: ConvictionLevel | null
  convictionScore: number | null
  convictionMethod: string | null
  entryZoneMethod: string | null
  tier: number | null
  peRatio: number | null
  roe: number | null
  dividendYield: number | null
  reviewFlags: string[]
  lastReviewedAt: string | null
  longtermNotes: string | null
  // Portfolio
  heldShares: number | null
  /** 0-1 continuous urgency within tier. 1 = about to trigger, 0 = far from threshold. */
  urgencyScore: number
}

// ─── Readiness Computation ───────────────────────────────────────────────────

const SWING_NEAR_ENTRY_RSI = 40
const SWING_SETTING_UP_RSI = 50
const LONGTERM_SETTING_UP_DISTANCE_PCT = 10

function computeSwingReadiness(rsi: number | null): ReadinessTier {
  if (rsi == null) return 'watching'
  if (rsi < SWING_NEAR_ENTRY_RSI) return 'near_entry'
  if (rsi < SWING_SETTING_UP_RSI) return 'setting_up'
  return 'watching'
}

function computeLongtermReadiness(proximity: EntryProximity | null): ReadinessTier {
  if (!proximity) return 'watching'
  if (proximity.isInZone) return 'near_entry'
  if (proximity.distancePct < LONGTERM_SETTING_UP_DISTANCE_PCT) return 'setting_up'
  return 'watching'
}

const TIER_PRIORITY: Record<ReadinessTier, number> = {
  near_entry: 0,
  setting_up: 1,
  watching: 2,
}

function pickMostUrgent(a: ReadinessTier, b: ReadinessTier): ReadinessTier {
  return TIER_PRIORITY[a] <= TIER_PRIORITY[b] ? a : b
}

/** Continuous 0-1 score: how close is this item to triggering the next tier up? */
function computeSwingUrgency(rsi: number | null): number {
  if (rsi == null) return 0
  if (rsi < SWING_NEAR_ENTRY_RSI) return 1.0
  if (rsi < SWING_SETTING_UP_RSI) {
    // 40→1.0, 50→0.0
    return 1 - (rsi - SWING_NEAR_ENTRY_RSI) / (SWING_SETTING_UP_RSI - SWING_NEAR_ENTRY_RSI)
  }
  return 0
}

function computeLongtermUrgency(proximity: EntryProximity | null): number {
  if (!proximity) return 0
  if (proximity.isInZone) return 1.0
  if (proximity.distancePct < LONGTERM_SETTING_UP_DISTANCE_PCT) {
    // 0%→1.0, 10%→0.0
    return 1 - proximity.distancePct / LONGTERM_SETTING_UP_DISTANCE_PCT
  }
  return 0
}

// ─── Merge Logic ─────────────────────────────────────────────────────────────

interface MergeInput {
  swingItems: SwingWatchlistItem[]
  longtermItems: LongtermWatchlistItem[]
  prices: Map<string, number> | undefined
  holdings: Map<string, number> | undefined
}

export function mergeWatchlists({
  swingItems, longtermItems, prices, holdings,
}: MergeInput): UnifiedWatchlistItem[] {
  const byTicker = new Map<string, UnifiedWatchlistItem>()

  // Process swing items
  for (const swing of swingItems) {
    const rsiClassification = classifyRsi(swing.rsi)
    const currentPrice = prices?.get(swing.ticker) ?? null
    const swingReadiness = computeSwingReadiness(swing.rsi)

    byTicker.set(swing.ticker, {
      ticker: swing.ticker,
      sectorName: swing.sector_name,
      plans: ['swing'],
      readiness: swingReadiness,
      currentPrice,
      rsi: swing.rsi != null ? Number(swing.rsi) : null,
      rsiZone: rsiClassification.zone,
      rsiLabel: rsiClassification.label,
      rsiBadgeClass: rsiClassification.badgeClass,
      stockType: swing.stock_type,
      isPinned: swing.is_pinned,
      pinReason: swing.pin_reason,
      swingNotes: swing.notes,
      entryZoneVnd: null, entryProximity: null, conviction: null,
      convictionScore: null, convictionMethod: null, entryZoneMethod: null,
      tier: null, peRatio: null, roe: null, dividendYield: null,
      reviewFlags: [], lastReviewedAt: null, longtermNotes: null,
      heldShares: holdings?.get(swing.ticker) ?? null,
      urgencyScore: computeSwingUrgency(swing.rsi != null ? Number(swing.rsi) : null),
    })
  }

  // Process longterm items — merge if ticker already exists
  for (const longterm of longtermItems) {
    const currentPrice = prices?.get(longterm.ticker) ?? null
    const proximity = currentPrice != null && longterm.entry_zone_vnd != null
      ? computeEntryProximity(currentPrice, Number(longterm.entry_zone_vnd))
      : null
    const longtermReadiness = computeLongtermReadiness(proximity)

    const longtermUrgency = computeLongtermUrgency(proximity)
    const existing = byTicker.get(longterm.ticker)
    if (existing) {
      // Merge longterm data into existing swing item
      existing.plans.push('longterm')
      existing.entryZoneVnd = longterm.entry_zone_vnd != null ? Number(longterm.entry_zone_vnd) : null
      existing.entryProximity = proximity
      existing.conviction = longterm.conviction
      existing.convictionScore = longterm.conviction_score
      existing.convictionMethod = longterm.conviction_method
      existing.entryZoneMethod = longterm.entry_zone_method
      existing.tier = longterm.tier
      existing.peRatio = longterm.pe_ratio
      existing.roe = longterm.roe
      existing.dividendYield = longterm.dividend_yield
      existing.reviewFlags = longterm.review_flags ?? []
      existing.lastReviewedAt = longterm.last_reviewed_at
      existing.longtermNotes = longterm.notes
      existing.readiness = pickMostUrgent(existing.readiness, longtermReadiness)
      existing.urgencyScore = Math.max(existing.urgencyScore, longtermUrgency)
    } else {
      byTicker.set(longterm.ticker, {
        ticker: longterm.ticker,
        sectorName: longterm.sector_name,
        plans: ['longterm'],
        readiness: longtermReadiness,
        currentPrice,
        rsi: null, rsiZone: null, rsiLabel: null, rsiBadgeClass: null,
        stockType: null, isPinned: false, pinReason: null, swingNotes: null,
        entryZoneVnd: longterm.entry_zone_vnd != null ? Number(longterm.entry_zone_vnd) : null,
        entryProximity: proximity,
        conviction: longterm.conviction,
        convictionScore: longterm.conviction_score,
        convictionMethod: longterm.conviction_method,
        entryZoneMethod: longterm.entry_zone_method,
        tier: longterm.tier,
        peRatio: longterm.pe_ratio,
        roe: longterm.roe,
        dividendYield: longterm.dividend_yield,
        reviewFlags: longterm.review_flags ?? [],
        lastReviewedAt: longterm.last_reviewed_at,
        longtermNotes: longterm.notes,
        heldShares: holdings?.get(longterm.ticker) ?? null,
        urgencyScore: longtermUrgency,
      })
    }
  }

  // Sort: by readiness tier, then by urgency within tier (higher urgency first)
  return [...byTicker.values()].sort((a, b) => {
    const tierDiff = TIER_PRIORITY[a.readiness] - TIER_PRIORITY[b.readiness]
    if (tierDiff !== 0) return tierDiff
    return b.urgencyScore - a.urgencyScore
  })
}

/** Items above this threshold get full rows; below get collapsed into overflow. */
export const HOT_URGENCY_THRESHOLD = 0.5

// ─── Readiness Tier Config ───────────────────────────────────────────────────

export const READINESS_CONFIG: Record<ReadinessTier, {
  label: string; badgeClass: string; description: string
}> = {
  near_entry: {
    label: 'Near Entry',
    badgeClass: 'bg-emerald-500/15 text-emerald-400',
    description: 'Actionable now — RSI oversold or price in entry zone',
  },
  setting_up: {
    label: 'Setting Up',
    badgeClass: 'bg-amber-500/15 text-amber-400',
    description: 'Approaching entry — watch closely',
  },
  watching: {
    label: 'Watching',
    badgeClass: 'bg-muted/40 text-muted-foreground',
    description: 'Not yet actionable',
  },
}

/** Group unified items by readiness tier (preserving sort within each group). */
export function groupByReadiness(
  items: UnifiedWatchlistItem[],
): { tier: ReadinessTier; items: UnifiedWatchlistItem[] }[] {
  const tiers: ReadinessTier[] = ['near_entry', 'setting_up', 'watching']
  return tiers
    .map((tier) => ({ tier, items: items.filter((item) => item.readiness === tier) }))
    // Always include near_entry so "Nothing actionable today" can render
    .filter((group) => group.tier === 'near_entry' || group.items.length > 0)
}
