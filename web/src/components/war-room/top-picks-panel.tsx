import { Link } from '@tanstack/react-router'
import { Sparkles, AlertCircle } from 'lucide-react'
import { Card } from '../ui/card'
import { Skeleton } from '../ui/skeleton'
import { Badge } from '../ui/badge'
import { cn, formatVND } from '../../lib/utils'
import { useScanDates, useRecommendations } from '../../hooks/use-intel'
import { ACTION_COLORS } from '../briefing/recommendations/shared'
import type { Recommendation } from '../../types/index'

function PickRow({
  rec,
  onTickerClick,
}: {
  rec: Recommendation
  onTickerClick?: (ticker: string) => void
}) {
  return (
    <div
      className="flex items-center gap-3 px-4 py-2.5 cursor-pointer hover:bg-muted/20 transition-colors"
      onClick={() => onTickerClick?.(rec.ticker)}
      data-test-id={`top-pick-${rec.ticker}`}
    >
      <Sparkles className="h-3 w-3 text-amber-400 shrink-0" />
      <span className="font-mono font-semibold text-sm w-12 shrink-0">{rec.ticker}</span>
      <Badge className={cn('text-[10px] px-1.5 py-0 h-4 shrink-0 font-mono', ACTION_COLORS[rec.action])}>
        {rec.action.replace('_', ' ')}
      </Badge>
      {rec.entry_price_vnd && (
        <span className="text-[10px] text-muted-foreground font-mono tabular-nums shrink-0">
          E {formatVND(rec.entry_price_vnd)}
        </span>
      )}
      {rec.stop_price_vnd && (
        <span className="text-[10px] text-rose-400/70 font-mono tabular-nums shrink-0">
          S {formatVND(rec.stop_price_vnd)}
        </span>
      )}
      {rec.target_price_vnd && (
        <span className="text-[10px] text-emerald-400/70 font-mono tabular-nums shrink-0">
          T {formatVND(rec.target_price_vnd)}
        </span>
      )}
      {rec.rationale && (
        <span className="text-[10px] text-muted-foreground truncate flex-1 min-w-0">
          {rec.rationale}
        </span>
      )}
    </div>
  )
}

interface TopPicksPanelProps {
  onTickerClick?: (ticker: string) => void
}

export function TopPicksPanel({ onTickerClick }: TopPicksPanelProps) {
  const { data: scanDates } = useScanDates()
  const latestDate = scanDates?.[0]
  const { data: recs, isLoading, error } = useRecommendations(latestDate)

  const topPicks = recs?.recommendations.filter((r) => r.section === 'TOP_PICKS') ?? []

  return (
    <Card className="border-border/50 py-0 gap-0 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/30">
        <div className="flex items-center gap-2">
          <Sparkles className="h-3 w-3 text-amber-400" />
          <h3 className="text-[10px] font-medium tracking-widest text-muted-foreground uppercase">
            Agent top picks
          </h3>
          {latestDate && (
            <span className="text-[10px] text-muted-foreground/50 font-mono">{latestDate}</span>
          )}
        </div>
        <Link
          to="/briefing" search={{} as any}
          className="text-[10px] text-muted-foreground hover:text-foreground transition-colors"
        >
          Briefing →
        </Link>
      </div>

      <div className="divide-y divide-border/20">
        {isLoading && Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 px-4 py-2.5">
            <Skeleton className="h-3 w-3 rounded-full" />
            <Skeleton className="h-4 w-12" />
            <Skeleton className="h-4 w-14" />
            <Skeleton className="h-3 w-40" />
          </div>
        ))}

        {error && (
          <div className="flex items-center gap-2 px-4 py-3 text-xs text-muted-foreground">
            <AlertCircle className="h-3 w-3 shrink-0" />
            <span>Could not load picks</span>
          </div>
        )}

        {!isLoading && !error && topPicks.length === 0 && (
          <p className="px-4 py-4 text-xs text-muted-foreground text-center">
            No top picks for today
          </p>
        )}

        {!isLoading && topPicks.map((rec) => (
          <PickRow key={rec.ticker} rec={rec as any} onTickerClick={onTickerClick} />
        ))}
      </div>
    </Card>
  )
}
