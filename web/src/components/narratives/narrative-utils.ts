import type { Narrative, NarrativeMomentum, NarrativeType, NarrativeMaturity } from '../../types/index'

export function deriveMomentum(narrative: Narrative): NarrativeMomentum {
  const daysSince = Math.floor(
    (Date.now() - new Date(narrative.last_seen).getTime()) / 86_400_000
  )
  const decayRatio = daysSince / Math.max(narrative.half_life_days, 1)
  if (decayRatio < 0.5 && narrative.article_count > 2) return 'Building'
  if (decayRatio > 1.5) return 'Fading'
  return 'Steady'
}

export function momentumBadgeClass(momentum: NarrativeMomentum): string {
  const map: Record<NarrativeMomentum, string> = {
    Building: 'bg-emerald-500/15 text-emerald-400',
    Steady: 'bg-amber-500/15 text-amber-400',
    Fading: 'bg-muted/50 text-muted-foreground',
  }
  return map[momentum] ?? map.Fading
}

export function convictionDotColor(score: number): string {
  if (score >= 0.7) return 'bg-emerald-400'
  if (score >= 0.5) return 'bg-emerald-400/70'
  if (score >= 0.3) return 'bg-amber-400/70'
  return 'bg-muted-foreground/40'
}

export const NARRATIVE_TYPE_LABELS: Record<NarrativeType, string> = {
  earnings: 'Earnings',
  regulatory: 'Regulatory',
  macro: 'Macro',
  corporate: 'Corporate',
  sector: 'Sector',
  geopolitical: 'Geopolitical',
  general: 'General',
}

export const MATURITY_LABELS: Record<NarrativeMaturity, string> = {
  emerging: 'Emerging',
  developing: 'Developing',
  confirmed: 'Confirmed',
  mature: 'Mature',
  fading: 'Fading',
  stale: 'Stale',
}
