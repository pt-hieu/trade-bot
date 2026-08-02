import { useMemo } from 'react'
import { Card } from '../ui/card'
import { Skeleton } from '../ui/skeleton'
import { PanelHeader, PanelError } from './panel'
import { cn, formatCompact, formatPct, plColor, toTitleCase } from '../../lib/utils'
import { usePortfolio } from '../../hooks/use-portfolio'
import type { PortfolioHolding } from '../../types/index'

interface PositionRowProps {
  holding: PortfolioHolding
  totalInvested: number
  livePl?: number
  livePlPct?: number
  onTickerClick?: (ticker: string) => void
}

function PositionRow({ holding, totalInvested, livePl, livePlPct, onTickerClick }: PositionRowProps) {
  const displayPl = livePl ?? holding.pl_vnd
  const displayPlPct = livePlPct ?? holding.pl_pct
  const weightPct = totalInvested > 0
    ? (Number(holding.market_value_vnd) / totalInvested) * 100
    : 0

  const plCls = plColor(displayPl)
  const barColor = displayPl >= 0 ? 'bg-emerald-500/30' : 'bg-rose-500/30'

  return (
    <div
      className="px-4 py-2.5 space-y-1 cursor-pointer hover:bg-muted/20 transition-colors"
      onClick={() => onTickerClick?.(holding.ticker)}
      data-test-id={`position-row-${holding.ticker}`}
    >
      <div className="flex items-center justify-between">
        <span
          className="font-mono font-semibold text-sm"
          data-test-id={`position-ticker-${holding.ticker}`}
        >
          {holding.ticker}
        </span>
        <div className="flex items-center gap-2">
          <span className={cn('font-mono text-xs font-semibold tabular-nums', plCls)}>
            {formatPct(displayPlPct)}
          </span>
          <span className={cn('font-mono text-[10px] tabular-nums', plCls)}>
            {displayPl >= 0 ? '+' : ''}{formatCompact(displayPl)}
          </span>
        </div>
      </div>
      {/* Weight bar */}
      <div className="h-1 w-full rounded-full bg-muted/40 overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all', barColor)}
          style={{ width: `${Math.min(weightPct, 100)}%` }}
        />
      </div>
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-muted-foreground">{holding.sector_name ? toTitleCase(holding.sector_name) : '—'}</span>
        <span className="text-[10px] text-muted-foreground font-mono tabular-nums">
          {weightPct.toFixed(1)}% weight
        </span>
      </div>
    </div>
  )
}

interface PositionsPanelProps {
  onTickerClick?: (ticker: string) => void
}

export function PositionsPanel({ onTickerClick }: PositionsPanelProps) {
  const { data: holdings, isLoading, error, refetch } = usePortfolio()

  const positions = useMemo(
    () => holdings?.filter((h) => h.holding_type !== 'Cash') ?? [],
    [holdings]
  )

  const totalInvested = useMemo(
    () => positions.reduce((sum, h) => sum + Number(h.market_value_vnd), 0),
    [positions]
  )

  // Sort by abs P/L descending (worst first — needs attention)
  const sorted = useMemo(
    () => [...positions].sort((a, b) => Math.abs(b.pl_vnd) - Math.abs(a.pl_vnd)),
    [positions]
  )

  return (
    <Card className="border-border/50 py-0 gap-0 overflow-hidden">
      <PanelHeader title="Positions" href="/portfolio" linkText="Portfolio →" />

      <div className="divide-y divide-border/20">
        {isLoading &&
          Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="px-4 py-2.5 space-y-1.5">
              <div className="flex justify-between">
                <Skeleton className="h-4 w-12" />
                <Skeleton className="h-4 w-16" />
              </div>
              <Skeleton className="h-1 w-full rounded-full" />
            </div>
          ))}

        {error && <PanelError message="Could not load positions" onRetry={refetch} />}

        {!isLoading && !error && sorted.length === 0 && (
          <p className="px-4 py-4 text-xs text-muted-foreground text-center">
            No open positions
          </p>
        )}

        {!isLoading &&
          sorted.map((holding, i) => (
            <PositionRow
              key={`${holding.ticker}-${i}`}
              holding={holding as any}
              totalInvested={totalInvested}
              onTickerClick={onTickerClick}
            />
          ))}
      </div>
    </Card>
  )
}
