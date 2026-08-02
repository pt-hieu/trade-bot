import { Link } from '@tanstack/react-router'
import { AlertCircle, ExternalLink } from 'lucide-react'
import { Card } from '../ui/card'
import { Skeleton } from '../ui/skeleton'
import { Badge } from '../ui/badge'
import { Tooltip, TooltipTrigger, TooltipContent } from '../ui/tooltip'
import { cn } from '../../lib/utils'
import { useMetricsByStrategy } from '../../hooks/use-metrics'
import { STRATEGY_BAR_COLOR, STRATEGY_BADGE_COLOR, STRATEGY_DEFINITIONS } from '../../lib/strategy'
import type { Strategy } from '../../lib/strategy'

export function StrategyWinRate() {
  const { data, isLoading, error, refetch } = useMetricsByStrategy()

  return (
    <Card className="border-border/50 py-0 gap-0 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/30">
        <h3 className="text-[10px] font-medium tracking-widest text-muted-foreground uppercase">
          Strategy
        </h3>
        <Link
          to="/trades" search={{} as any}
          className="text-[10px] text-muted-foreground hover:text-foreground transition-colors"
        >
          Trades →
        </Link>
      </div>

      <div className="px-4 py-3 space-y-2.5">
        {isLoading && (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="space-y-1">
              <div className="flex justify-between">
                <Skeleton className="h-3 w-16" />
                <Skeleton className="h-3 w-12" />
              </div>
              <Skeleton className="h-1.5 w-full rounded-full" />
            </div>
          ))
        )}

        {error && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <AlertCircle className="h-3 w-3" />
            <button onClick={() => refetch()} className="hover:text-foreground transition-colors">
              Data unavailable — retry
            </button>
          </div>
        )}

        {!isLoading && !error && data?.length === 0 && (
          <p className="text-xs text-muted-foreground">
            No closed trades yet.
          </p>
        )}

        {!isLoading && !error && data?.filter((s) => s.strategy).map((s) => {
          const winRate = Number(s.win_rate)
          const barColor = STRATEGY_BAR_COLOR[s.strategy] ?? 'bg-muted-foreground'
          const badgeClass = STRATEGY_BADGE_COLOR[s.strategy] ?? 'bg-muted/40 text-muted-foreground border-border/40'
          const definition = STRATEGY_DEFINITIONS[s.strategy as Strategy]

          return (
            <Link
              key={s.strategy}
              to="/trades" search={{ strategy: s.strategy } as any}
              className="block space-y-1 group cursor-pointer rounded hover:bg-muted/20 -mx-1 px-1 py-0.5 transition-colors"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Badge className={cn('text-[10px] px-1.5 py-0 h-4 shrink-0', badgeClass)}>
                        {s.strategy}
                      </Badge>
                    </TooltipTrigger>
                    {definition && (
                      <TooltipContent side="right" className="max-w-[240px]">
                        {definition}
                      </TooltipContent>
                    )}
                  </Tooltip>
                  <ExternalLink className="h-2.5 w-2.5 text-muted-foreground/0 group-hover:text-muted-foreground/50 transition-colors" />
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="font-mono text-xs tabular-nums">
                    {winRate.toFixed(0)}%
                  </span>
                  <span className="text-[10px] text-muted-foreground font-mono tabular-nums">
                    {s.wins}W/{s.losses}L
                  </span>
                </div>
              </div>
              <div className="h-1.5 rounded-full bg-muted/30 overflow-hidden">
                <div
                  className={cn('h-full rounded-full', barColor)}
                  style={{ width: `${winRate}%` }}
                />
              </div>
            </Link>
          )
        })}
      </div>
    </Card>
  )
}
