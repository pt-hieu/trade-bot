import { AlertTriangle } from 'lucide-react'
import { cn } from '../../lib/utils'
import { IMPACT_LABELS } from '../catalysts-utils'
import { MATURITY_LABELS } from '../narratives/narrative-utils'
import { scoreBarColor, scoreTextColor, scoreCatalyst } from './newsroom-utils'
import { toTitleCase } from '../../lib/utils'
import type { Narrative, Catalyst } from '../../types/index'
import type { FeedItem } from './feed-card'

function daysUntil(dateString: string): number {
  const target = new Date(dateString)
  const now = new Date()
  return Math.max(0, Math.ceil((target.getTime() - now.getTime()) / 86_400_000))
}

interface SpotlightStripProps {
  themes: Narrative[]
  catalysts: Catalyst[]
  onSelect: (item: FeedItem) => void
}

export function SpotlightStrip({ themes, catalysts, onSelect }: SpotlightStripProps) {
  if (themes.length === 0 && catalysts.length === 0) return null

  return (
    <div className="flex gap-2.5 overflow-x-auto pb-1 scrollbar-hide">
      {themes.map((narrative) => {
        const convictionPct = Math.round(narrative.conviction_score * 100)
        return (
          <button
            key={narrative.id}
            type="button"
            onClick={() => onSelect({ type: 'theme', data: narrative, score: narrative.conviction_score })}
            className="shrink-0 w-[220px] text-left rounded-lg border border-border/30 bg-muted/10 px-3 py-2 hover:bg-muted/20 hover:border-border/50 transition-colors cursor-pointer space-y-1"
          >
            <div className="flex items-center justify-between">
              <span className="text-[9px] uppercase tracking-wider font-medium text-blue-400/70">Theme</span>
              <div className="flex items-center gap-1.5">
                <span className={cn('font-mono text-[10px] font-semibold tabular-nums', scoreTextColor(narrative.conviction_score))}>
                  {convictionPct}
                </span>
                <div className="w-6 h-[3px] rounded-full bg-muted/30 overflow-hidden">
                  <div
                    className={cn('h-full rounded-full', scoreBarColor(narrative.conviction_score))}
                    style={{ width: `${convictionPct}%` }}
                  />
                </div>
              </div>
            </div>
            <p className="text-[12px] font-medium text-foreground/90 leading-snug line-clamp-2">{narrative.theme}</p>
            <div className="flex items-center gap-1 text-[9px] text-muted-foreground/50">
              <span>{MATURITY_LABELS[narrative.maturity]}</span>
              <span className="text-muted-foreground/20">·</span>
              <span>{narrative.article_count} articles</span>
            </div>
          </button>
        )
      })}
      {catalysts.length > 0 && themes.length > 0 && (
        <span className="w-px bg-border/30 shrink-0 my-1" />
      )}
      {catalysts.map((catalyst) => {
        const remainingDays = catalyst.expected_date ? daysUntil(catalyst.expected_date) : null
        return (
          <button
            key={catalyst.id}
            type="button"
            onClick={() => onSelect({ type: 'catalyst', data: catalyst, score: scoreCatalyst(catalyst) })}
            className="shrink-0 w-[220px] text-left rounded-lg border border-amber-500/20 bg-amber-500/[0.04] px-3 py-2 hover:bg-amber-500/[0.08] hover:border-amber-500/30 transition-colors cursor-pointer space-y-1"
          >
            <div className="flex items-center justify-between">
              <span className="text-[9px] uppercase tracking-wider font-medium text-amber-400/80">Imminent</span>
              {remainingDays !== null && (
                <span className="font-mono text-[10px] text-amber-400/70">{remainingDays}d</span>
              )}
            </div>
            <p className="text-[12px] font-medium text-foreground/90 leading-snug line-clamp-2">{catalyst.event}</p>
            <div className="flex items-center gap-1 text-[9px] text-muted-foreground/50">
              <span>{IMPACT_LABELS[catalyst.impact] ?? catalyst.impact}</span>
              <span className="text-muted-foreground/20">·</span>
              <span>{toTitleCase(catalyst.confidence)}</span>
            </div>
          </button>
        )
      })}
    </div>
  )
}
