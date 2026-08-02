// Watchlist utilities: price derivation, entry proximity, 30d change.

// ─── Price Derivation ────────────────────────────────────────────────────────

/** Extract current price from sparkline data (last close, in thousands VND). */
export function extractCurrentPrice(
  sparklineData: { close: number }[] | undefined,
): number | null {
  if (!sparklineData?.length) return null
  const lastClose = sparklineData[sparklineData.length - 1].close
  return Number.isFinite(lastClose) ? lastClose : null
}

/** Format thousands-VND price to display string. */
export function formatPriceVnd(priceThousands: number): string {
  return Math.round(priceThousands * 1000).toLocaleString('vi-VN')
}

// ─── 30d Price Change (for non-chart rows) ──────────────────────────────────

export interface PriceChange {
  pct: number
  direction: 'up' | 'down' | 'flat'
}

/** Compute 30-day price change from sparkline close data. */
export function compute30dChange(bars: { close: number }[] | undefined): PriceChange | undefined {
  if (!bars || bars.length < 2) return undefined
  const first = bars[0].close
  const last = bars[bars.length - 1].close
  if (!Number.isFinite(first) || !Number.isFinite(last) || first === 0) return undefined
  const pct = ((last - first) / first) * 100
  return { pct, direction: pct > 0.5 ? 'up' : pct < -0.5 ? 'down' : 'flat' }
}

// ─── Entry Proximity (Long-Term) ─────────────────────────────────────────────

export interface EntryProximity {
  /** Negative = below entry zone (good), positive = above */
  distancePct: number
  isInZone: boolean
  colorClass: string
}

/**
 * Compare current price to entry zone.
 * @param currentPriceThousands - current price in thousands VND (from sparkline)
 * @param entryZoneVnd - entry zone in raw VND (from DB)
 */
export function computeEntryProximity(
  currentPriceThousands: number,
  entryZoneVnd: number,
): EntryProximity {
  const currentVnd = currentPriceThousands * 1000
  const distancePct = ((currentVnd - entryZoneVnd) / entryZoneVnd) * 100
  const isInZone = currentVnd <= entryZoneVnd

  return {
    distancePct,
    isInZone,
    colorClass: isInZone
      ? 'text-emerald-400'
      : distancePct < 10
        ? 'text-amber-400'
        : 'text-rose-400',
  }
}