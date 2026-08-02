import { Telescope } from 'lucide-react'
import { Card } from '../../ui/card'
import { TooltipProvider } from '../../ui/tooltip'
import { InsightToggle, InsightTrigger, InsightCard } from '../../ui/detail-text'
import { toTitleCase } from '../../../lib/utils'
import type { RecommendationsData } from '../../../types/index'
import { SECTION_LABELS, CardLabel } from './shared'
import { SectionTable } from './tables'
import type { SectionKey } from './shared'

// ── Summary Row ──────────────────────────────────────────────────────────────

function SummaryRow({ data }: { data: RecommendationsData }) {
  const entryHitPct = Number(data.entry_hit_rate ?? 0)
  const winRatePct = Number(data.win_rate ?? 0)
  const entryHitColor = entryHitPct >= 50 ? 'text-emerald-400' : 'text-rose-400'
  const winRateColor = winRatePct >= 50 ? 'text-emerald-400' : 'text-rose-400'

  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex gap-3 flex-wrap">
        <Card className="border-border/50 py-2 px-3 flex-1 min-w-[100px]">
          <CardLabel label="Recs" tip="Total actionable recommendations (excludes AVOID/WAIT/WATCH/SKIP)" />
          <p className="text-lg font-semibold font-mono tabular-nums">{data.total_recs ?? 0}</p>
        </Card>
        <Card gradient={entryHitPct >= 50 ? 'positive' : 'negative'} className="border-border/50 py-2 px-3 flex-1 min-w-[100px]">
          <CardLabel label="Entry Hit" tip="% of BUY/ADD recs where intraday low reached entry price" />
          <p className={`text-lg font-semibold font-mono tabular-nums ${entryHitColor}`}>
            {data.entry_hit_rate != null ? `${Number(data.entry_hit_rate).toFixed(0)}%` : '—'}
          </p>
        </Card>
        <Card gradient={winRatePct >= 50 ? 'positive' : 'negative'} className="border-border/50 py-2 px-3 flex-1 min-w-[100px]">
          <CardLabel label="Win Rate" tip="% of actionable recs that were correct. WIN or HOLD with positive P/L count as wins." />
          <p className={`text-lg font-semibold font-mono tabular-nums ${winRateColor}`}>
            {data.win_rate != null ? `${Number(data.win_rate).toFixed(0)}%` : '—'}
          </p>
        </Card>
        {data.trading_mode && (
          <Card className="border-border/50 py-2 px-3 flex-1 min-w-[100px]">
            <CardLabel label="Mode" tip="NORMAL: all strategies valid. LOW_CASH: only TRIM/EXIT. REALLOCATION: only EXIT stagnant positions." />
            <p className="text-lg font-semibold font-mono tabular-nums">{toTitleCase(data.trading_mode)}</p>
          </Card>
        )}
      </div>
    </TooltipProvider>
  )
}

// ── Main ─────────────────────────────────────────────────────────────────────

interface RecommendationsSectionProps {
  data: RecommendationsData
}

export function RecommendationsSection({ data }: RecommendationsSectionProps) {
  const { recommendations } = data

  const sections: SectionKey[] = ['MY_HOLDINGS', 'TOP_PICKS', 'LONG_TERM', 'SKIP_THESE']
  const grouped = sections.map((s) => ({
    section: s,
    recs: recommendations.filter((r) => r.section === s),
  })).filter((g) => g.recs.length > 0 || g.section === 'TOP_PICKS')

  // Add ungrouped
  const knownSections = new Set<string>(sections)
  const ungrouped = recommendations.filter((r) => !r.section || !knownSections.has(r.section))
  if (ungrouped.length > 0) grouped.push({ section: 'OTHER' as SectionKey, recs: ungrouped })

  const hasInsight = !!(data.key_insight || data.best_call || data.worst_call)

  return (
    <InsightToggle>
    <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-500" style={{ animationDelay: '300ms' }}>
      <div className="flex items-center gap-3">
        {hasInsight && <InsightTrigger />}
      </div>

      <SummaryRow data={data} />

      {/* Insights (toggled) */}
      {hasInsight && (
        <InsightCard>
          {data.key_insight && (
            <p><span className="text-amber-400 font-medium">Insight:</span> {data.key_insight}</p>
          )}
          {data.best_call && (
            <p><span className="text-emerald-400 font-medium">Best:</span> {data.best_call}</p>
          )}
          {data.worst_call && (
            <p><span className="text-rose-400 font-medium">Worst:</span> {data.worst_call}</p>
          )}
        </InsightCard>
      )}

      {grouped.map(({ section, recs }) => (
        <div key={section} className="space-y-2">
          <h3 className="text-xs font-medium tracking-widest text-muted-foreground uppercase">
            {SECTION_LABELS[section] ?? section.replace(/_/g, ' ')}
          </h3>
          {recs.length === 0 && section === 'TOP_PICKS' ? (
            <div className="flex items-center gap-2.5 rounded-lg border border-border/40 border-dashed px-4 py-4 text-zinc-500">
              <Telescope className="h-4 w-4 shrink-0" />
              <span className="text-xs">No top picks today — watchlist had no qualifying setups meeting risk criteria.</span>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border/50">
              <TooltipProvider delayDuration={200}>
                <SectionTable section={section} recs={recs} />
              </TooltipProvider>
            </div>
          )}
        </div>
      ))}

    </div>
    </InsightToggle>
  )
}
