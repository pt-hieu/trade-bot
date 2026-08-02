// Centralized RSI classification — single source of truth for zones, labels, and badge styling.

export type RsiZone = 'oversold' | 'setup' | 'neutral' | 'overbought'

export interface RsiClassification {
  zone: RsiZone
  label: string
  badgeClass: string
}

const ZONES: Record<RsiZone, Omit<RsiClassification, 'zone'>> = {
  oversold: {
    label: 'Oversold',
    badgeClass: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
  },
  setup: {
    label: 'Setup',
    badgeClass: 'bg-amber-500/15 text-amber-400 border-amber-500/20',
  },
  neutral: {
    label: 'Neutral',
    badgeClass: 'bg-muted/40 text-muted-foreground border-border/40',
  },
  overbought: {
    label: 'Overbought',
    badgeClass: 'bg-rose-500/15 text-rose-400 border-rose-500/20',
  },
}

export function classifyRsi(rsi: number | string | null): RsiClassification {
  if (rsi == null) return { zone: 'neutral', ...ZONES.neutral }
  const value = Number(rsi)
  if (isNaN(value)) return { zone: 'neutral', ...ZONES.neutral }

  if (value < 30) return { zone: 'oversold', ...ZONES.oversold }
  if (value < 50) return { zone: 'setup', ...ZONES.setup }
  if (value > 70) return { zone: 'overbought', ...ZONES.overbought }
  return { zone: 'neutral', ...ZONES.neutral }
}

/** Sort priority: oversold=0 (most actionable), setup=1, neutral=2, overbought=3, null=99 */
const ZONE_PRIORITY: Record<RsiZone, number> = {
  oversold: 0,
  setup: 1,
  neutral: 2,
  overbought: 3,
}

export function getRsiSortPriority(rsi: number | string | null): number {
  if (rsi == null) return 99
  return ZONE_PRIORITY[classifyRsi(rsi).zone]
}
