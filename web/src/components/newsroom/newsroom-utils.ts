import { formatMinDate, formatShortDate } from '../../lib/date'
import type { Narrative, Catalyst, NarrativeMaturity } from '../../types/index'

export function scoreBarColor(score: number): string {
  if (score >= 0.7) return 'bg-emerald-500'
  if (score >= 0.5) return 'bg-emerald-500/60'
  if (score >= 0.3) return 'bg-amber-500/60'
  return 'bg-muted-foreground/30'
}

export function scoreTextColor(score: number): string {
  if (score >= 0.7) return 'text-emerald-400'
  if (score >= 0.5) return 'text-emerald-400/70'
  if (score >= 0.3) return 'text-amber-400/70'
  return 'text-muted-foreground/50'
}

export function maturityDotColor(maturity: NarrativeMaturity): string {
  const map: Record<NarrativeMaturity, string> = {
    mature: 'bg-purple-400',
    confirmed: 'bg-emerald-400',
    developing: 'bg-blue-400',
    emerging: 'bg-muted-foreground/40',
    fading: 'bg-amber-400',
    stale: 'bg-muted-foreground/20',
  }
  return map[maturity] ?? map.emerging
}

export function formatNarrativeDateRange(narrative: Narrative): string {
  return narrative.first_seen === narrative.last_seen
    ? formatMinDate(narrative.last_seen)
    : `${formatMinDate(narrative.first_seen)} – ${formatMinDate(narrative.last_seen)}`
}

export function formatCatalystDate(catalyst: Catalyst): string {
  return catalyst.expected_date ? formatShortDate(catalyst.expected_date) : catalyst.expected
}

/** Score a catalyst on 0-1 scale to mix with narrative conviction scores */
export function scoreCatalyst(catalyst: Catalyst): number {
  let score = 0.3
  if (catalyst.confidence === 'HIGH') score += 0.3
  else if (catalyst.confidence === 'MEDIUM') score += 0.15
  if (catalyst.status === 'imminent') score += 0.3
  else if (catalyst.status === 'active') score += 0.1
  if (catalyst.impact === 'POSITIVE' || catalyst.impact === 'NEGATIVE') score += 0.1
  return Math.min(score, 1)
}
