// Shared badge styling and label helpers for catalysts + capital events

export function impactBadge(impact: string) {
  if (impact === 'POSITIVE') return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20'
  if (impact.startsWith('NEGATIVE')) return 'bg-rose-500/15 text-rose-400 border-rose-500/20'
  return 'bg-amber-500/15 text-amber-400 border-amber-500/20'
}

export function confidenceBadge(confidence: string) {
  if (confidence === 'HIGH') return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20'
  if (confidence === 'LOW') return 'bg-rose-500/15 text-rose-400 border-rose-500/20'
  return 'bg-amber-500/15 text-amber-400 border-amber-500/20'
}

export function statusBadge(status: string) {
  if (status === 'active') return 'bg-blue-500/15 text-blue-400 border-blue-500/20'
  if (status === 'monitoring') return 'bg-cyan-500/15 text-cyan-400 border-cyan-500/20'
  if (status === 'imminent') return 'bg-amber-500/15 text-amber-400 border-amber-500/20'
  if (status === 'resolved') return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20'
  if (status === 'expired') return 'bg-muted/30 text-muted-foreground/60 border-muted-foreground/10'
  return 'bg-muted text-muted-foreground'
}

export const EVENT_TYPE_LABELS: Record<string, string> = {
  capital_increase: 'Capital Increase',
  ipo: 'IPO',
  stock_split: 'Stock Split',
  ma: 'M&A',
  buyback: 'Buyback',
  dividend: 'Dividend',
}

export const IMPACT_LABELS: Record<string, string> = {
  POSITIVE: 'Positive',
  NEGATIVE: 'Negative',
  NEGATIVE_SHORT_TERM: 'Negative Short Term',
  NEGATIVE_LONG_TERM: 'Negative Long Term',
  NEUTRAL: 'Neutral',
  WATCH: 'Watch',
}
