import { Link } from '@tanstack/react-router'
import { Card } from '../ui/card'
import { Skeleton } from '../ui/skeleton'
import { Badge } from '../ui/badge'
import { cn, formatCompact, toTitleCase } from '../../lib/utils'
import type { ForeignFlowData, FlowSignal, FlowPattern } from '../../types/index'

const SIGNAL_CLASS: Record<FlowSignal, string> = {
  RISK_ON: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
  RISK_OFF: 'bg-rose-500/15 text-rose-400 border-rose-500/20',
  NEUTRAL: 'bg-muted/40 text-muted-foreground border-border/40',
}

const PATTERN_CLASS: Record<FlowPattern, string> = {
  Accumulation: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
  Distribution: 'bg-rose-500/15 text-rose-400 border-rose-500/20',
  Neutral: 'bg-muted/40 text-muted-foreground border-border/40',
}

interface ForeignFlowMiniProps {
  flow: ForeignFlowData | null | undefined
  isLoading: boolean
}

export function ForeignFlowMini({ flow, isLoading }: ForeignFlowMiniProps) {
  const net = flow?.net_value_billion ?? null
  const netColor = net == null ? '' : net >= 0 ? 'text-emerald-500' : 'text-rose-500'

  return (
    <Card className="border-border/50 py-0 gap-0 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/30">
        <h3 className="text-[10px] font-medium tracking-widest text-muted-foreground uppercase">
          Foreign flow
        </h3>
        <Link
          to="/briefing" search={{} as any}
          className="text-[10px] text-muted-foreground hover:text-foreground transition-colors"
        >
          Briefing →
        </Link>
      </div>

      <div className="px-4 py-3 space-y-2.5">
        {isLoading && (
          <>
            <Skeleton className="h-6 w-24" />
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-3 w-full" />
          </>
        )}

        {!isLoading && !flow && (
          <p className="text-xs text-muted-foreground">Flow data unavailable</p>
        )}

        {!isLoading && flow && (
          <>
            {/* Net value + badges */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className={cn('font-mono text-xl font-semibold tabular-nums', netColor)}>
                {net != null ? `${net >= 0 ? '+' : ''}${formatCompact(net * 1_000_000_000)}` : '—'}
              </span>
              {flow.signal && (
                <Badge className={cn('text-[10px] px-1.5 py-0 h-4', SIGNAL_CLASS[flow.signal])}>
                  {toTitleCase(flow.signal)}
                </Badge>
              )}
              {flow.pattern && (
                <Badge className={cn('text-[10px] px-1.5 py-0 h-4', PATTERN_CLASS[flow.pattern])}>
                  {flow.pattern}
                </Badge>
              )}
            </div>

            {/* Top bought */}
            {flow.top_bought.length > 0 && (
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] text-emerald-400 shrink-0">Bought</span>
                <div className="flex gap-1 flex-wrap">
                  {flow.top_bought.slice(0, 3).map((t) => (
                    <span key={t.ticker} className="font-mono text-[10px] text-foreground/80">
                      {t.ticker}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Top sold */}
            {flow.top_sold.length > 0 && (
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] text-rose-400 shrink-0">Sold</span>
                <div className="flex gap-1 flex-wrap">
                  {flow.top_sold.slice(0, 3).map((t) => (
                    <span key={t.ticker} className="font-mono text-[10px] text-foreground/80">
                      {t.ticker}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </Card>
  )
}
