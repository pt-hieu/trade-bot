import { Card } from '../ui/card'
import { CardLabel } from '../ui/card-label'
import { formatShortDate } from '../../lib/date'
import { accuracyColor } from '../../lib/utils'
import type { EnrichedLearningSummary } from '../../types/index'

const HEALTH_TINT: Record<string, string> = {
  'text-emerald-400': 'bg-emerald-500/10 border-emerald-500/20',
  'text-amber-400': 'bg-amber-500/10 border-amber-500/20',
  'text-rose-400': 'bg-rose-500/10 border-rose-500/20',
}

function tintFromColor(colorClass: string): string {
  return HEALTH_TINT[colorClass] ?? 'border-border/50'
}

export function SummaryStats({ summary }: { summary: EnrichedLearningSummary | null }) {
  if (!summary) return null

  const winRate = Number(summary.overall_win_rate ?? 0)
  const pnl = Number(summary.avg_pnl_percent ?? 0)
  const entryHit = Number(summary.overall_entry_hit_rate ?? 0)
  const freshness = summary.last_updated ? formatShortDate(summary.last_updated) : ''

  const entryHitColorClass = accuracyColor(entryHit / 100, { high: 0.40, mid: 0.25 })
  const winRateColorClass = winRate >= 50 ? 'text-emerald-400' : 'text-rose-400'
  const pnlColorClass = pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'

  return (
    <div className="space-y-1.5">
      {freshness && (
        <p className="text-[10px] text-muted-foreground/60 font-mono">
          Updated {freshness} · {summary.total_days}d rolling window
        </p>
      )}
      <div className="flex gap-3 flex-wrap">
        <Card className="border-border/50 py-2 px-3 flex-1 min-w-[90px]">
          <CardLabel label="Days" tip="Rolling window of trading days analyzed" />
          <p className="text-lg font-semibold font-mono tabular-nums text-muted-foreground">{summary.total_days}</p>
        </Card>
        <Card className="border-border/50 py-2 px-3 flex-1 min-w-[90px]">
          <CardLabel label="Recs" tip="Total recommendations analyzed in the window" />
          <p className="text-lg font-semibold font-mono tabular-nums text-muted-foreground">{summary.total_recs}</p>
        </Card>

        <Card className={`py-2 px-3 flex-1 min-w-[90px] ${tintFromColor(entryHitColorClass)}`}>
          <CardLabel label="Entry Hit" tip="% of BUY/ADD recs where price hit entry. Excludes AVOID/HOLD/SKIP." />
          <p className={`text-lg font-semibold font-mono tabular-nums ${entryHitColorClass}`}>
            {summary.overall_entry_hit_rate != null ? `${entryHit.toFixed(0)}%` : '—'}
          </p>
        </Card>
        <Card className={`py-2 px-3 flex-1 min-w-[90px] ${tintFromColor(winRateColorClass)}`}>
          <CardLabel label="Win Rate" tip="% of all recs that were correct. AVOID that avoided losses count as wins." />
          <p className={`text-lg font-semibold font-mono tabular-nums ${winRateColorClass}`}>
            {winRate ? `${winRate.toFixed(0)}%` : '—'}
          </p>
        </Card>
        <Card className={`py-2 px-3 flex-1 min-w-[90px] ${tintFromColor(pnlColorClass)}`}>
          <CardLabel label="Avg P/L" tip="Average profit/loss on trades where entry was hit" />
          <p className={`text-lg font-semibold font-mono tabular-nums ${pnlColorClass}`}>
            {summary.avg_pnl_percent != null
              ? `${pnl >= 0 ? '+' : ''}${pnl.toFixed(1)}%`
              : '—'}
          </p>
        </Card>
      </div>
    </div>
  )
}
