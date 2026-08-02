import { useState, useMemo } from 'react'
import { Link } from '@tanstack/react-router'
import { ArrowRight, History, Zap } from 'lucide-react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table'
import { Badge } from '../ui/badge'
import { Skeleton } from '../ui/skeleton'
import { Sparkline } from '../ui/sparkline'
import { cn, toTitleCase } from '../../lib/utils'
import { STRATEGY_BADGE_COLOR } from '../../lib/strategy'
import { formatMinDate } from '../../lib/date'
import { useSparklineData } from '../../hooks/use-sparkline-data'
import type { EnhancedHolding, TickerContext } from '../../types/index'

function vsStopColor(vsStopPct: number | null): string {
  if (vsStopPct === null) return 'text-muted-foreground/50'
  if (vsStopPct > 10) return 'text-emerald-400'
  if (vsStopPct >= 5) return 'text-amber-400'
  return 'text-rose-400'
}

interface EnhancedHoldingsProps {
  holdings: EnhancedHolding[]
  tickerContext?: Map<string, TickerContext>
}

export function EnhancedHoldingsTable({ holdings, tickerContext }: EnhancedHoldingsProps) {
  const [groupByTicker, setGroupByTicker] = useState(true)
  const tickers = useMemo(
    () => [...new Set(holdings.map((holding) => holding.ticker))],
    [holdings]
  )
  const { data: sparklines } = useSparklineData(tickers)

  const displayHoldings = groupByTicker ? groupHoldingsByTicker(holdings) : holdings

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="text-[10px] font-medium tracking-widest text-muted-foreground uppercase">
          Current holdings
        </p>
        <button
          onClick={() => setGroupByTicker(!groupByTicker)}
          className="text-[10px] font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
        >
          {groupByTicker ? 'Show individual lots' : 'Group by ticker'}
        </button>
      </div>

      <div className="rounded-lg border border-border/50 overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-[130px]">Ticker</TableHead>
              <TableHead>Sector</TableHead>
              <TableHead className="text-right">Since</TableHead>
              <TableHead className="text-right">Shares</TableHead>
              <TableHead className="text-right">Avg cost</TableHead>
              <TableHead className="text-right">Current</TableHead>
              <TableHead className="text-right w-[70px]">vs Stop</TableHead>
              <TableHead className="text-center w-[106px]">30D</TableHead>
              <TableHead className="text-right w-[70px]">P/L %</TableHead>
              <TableHead className="w-[100px]" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {displayHoldings.map((holding, index) => {
              const plPct = Number(holding.plPct)
              const plColor = plPct > 0 ? 'text-emerald-400' : plPct < 0 ? 'text-rose-400' : ''
              const sparklineData = sparklines?.[holding.ticker]
              const context = tickerContext?.get(holding.ticker)
              const contextTotal = context
                ? context.catalystCount + context.narrativeCount + context.capitalEventCount
                : 0

              return (
                <TableRow key={`${holding.ticker}-${index}`}>
                  <TableCell>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="font-mono font-semibold">{holding.ticker}</span>
                      {holding.strategy && (
                        <Badge className={`text-[9px] px-1.5 py-0 ${STRATEGY_BADGE_COLOR[holding.strategy] || 'bg-muted text-muted-foreground border-border'}`}>
                          {holding.strategy}
                        </Badge>
                      )}
                      <Badge className={cn(
                        'text-[9px] px-1.5 py-0',
                        holding.systemAligned
                          ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20'
                          : 'bg-amber-500/15 text-amber-400 border-amber-500/20'
                      )}>
                        {holding.systemAligned ? 'Aligned' : 'Override'}
                      </Badge>
                      {contextTotal > 0 && (
                        <Link
                          to="/newsroom"
                          search={{ ticker: holding.ticker } as any}
                          className={cn(
                            'inline-flex items-center gap-0.5 text-[9px] px-1.5 py-0 rounded-full border cursor-pointer transition-colors',
                            context?.hasNegative
                              ? 'bg-amber-500/15 text-amber-400 border-amber-500/20 hover:bg-amber-500/25'
                              : 'bg-violet-500/15 text-violet-400 border-violet-500/20 hover:bg-violet-500/25'
                          )}
                        >
                          <Zap className="h-2.5 w-2.5" />
                          {contextTotal}
                        </Link>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {holding.sectorName ? toTitleCase(holding.sectorName) : '—'}
                  </TableCell>
                  <TableCell className="text-right text-xs font-mono tabular-nums">
                    {holding.entryDate ? formatMinDate(holding.entryDate) : '—'}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums text-xs">
                    {Number(holding.shares).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums text-xs">
                    {Number(holding.avgCostVnd).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums text-xs">
                    {holding.currentPriceVnd ? Number(holding.currentPriceVnd).toLocaleString() : '—'}
                  </TableCell>
                  <TableCell className={cn('text-right font-mono tabular-nums text-xs', vsStopColor(holding.vsStopPct))}>
                    {holding.vsStopPct !== null ? `${holding.vsStopPct > 0 ? '+' : ''}${holding.vsStopPct.toFixed(1)}%` : '—'}
                  </TableCell>
                  <TableCell className="text-center">
                    {sparklineData ? (
                      <div className="flex justify-center">
                        <Sparkline
                          data={sparklineData}
                          width={90}
                          height={28}
                          costBasis={holding.avgCostVnd / 1000}
                          stopPrice={holding.stopPriceVnd ? holding.stopPriceVnd / 1000 : undefined}
                          plPct={Number(holding.plPct)}
                        />
                      </div>
                    ) : (
                      <Skeleton className="h-7 w-[90px] mx-auto" />
                    )}
                  </TableCell>
                  <TableCell className={cn('text-right font-mono tabular-nums text-xs font-medium', plColor)}>
                    {plPct !== 0 ? `${plPct >= 0 ? '+' : ''}${plPct.toFixed(2)}%` : '—'}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2 justify-end">
                      <Link
                        to="/trades"
                        search={{ ticker: holding.ticker } as any}
                        className="inline-flex items-center gap-0.5 text-[10px] text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                      >
                        <History className="h-3 w-3" />
                        History
                      </Link>
                      <Link
                        to="/trades"
                        search={{ ticker: holding.ticker } as any}
                        className="inline-flex items-center gap-0.5 text-[10px] text-rose-400 hover:text-rose-300 transition-colors cursor-pointer"
                      >
                        Exit
                        <ArrowRight className="h-3 w-3" />
                      </Link>
                    </div>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

function groupHoldingsByTicker(holdings: EnhancedHolding[]): EnhancedHolding[] {
  const grouped = new Map<string, EnhancedHolding[]>()
  for (const holding of holdings) {
    const existing = grouped.get(holding.ticker) || []
    existing.push(holding)
    grouped.set(holding.ticker, existing)
  }

  return [...grouped.entries()].map(([, tickerHoldings]) => {
    if (tickerHoldings.length === 1) return tickerHoldings[0]

    const totalShares = tickerHoldings.reduce((sum, holding) => sum + holding.shares, 0)
    const totalCostBasis = tickerHoldings.reduce((sum, holding) => sum + holding.costBasisVnd, 0)
    const totalMarketValue = tickerHoldings.reduce((sum, holding) => sum + holding.marketValueVnd, 0)
    const totalWeight = tickerHoldings.reduce((sum, holding) => sum + holding.weightPct, 0)
    const avgCost = totalShares > 0 ? Math.round(totalCostBasis / totalShares) : 0
    const plVnd = totalMarketValue - totalCostBasis
    const plPct = totalCostBasis > 0 ? (plVnd / totalCostBasis) * 100 : 0

    const earliest = tickerHoldings.reduce((earliestHolding, holding) => {
      if (!holding.entryDate) return earliestHolding
      if (!earliestHolding.entryDate) return holding
      return holding.entryDate < earliestHolding.entryDate ? holding : earliestHolding
    })

    return {
      ...earliest,
      shares: totalShares,
      avgCostVnd: avgCost,
      costBasisVnd: totalCostBasis,
      marketValueVnd: totalMarketValue,
      plVnd,
      plPct,
      weightPct: totalWeight,
      daysHeld: tickerHoldings.reduce((max, holding) => Math.max(max, holding.daysHeld || 0), 0),
      systemAligned: tickerHoldings.every((holding) => holding.systemAligned),
    }
  })
}

export function EnhancedHoldingsSkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-4 w-32" />
      <Skeleton className="h-[200px] w-full" />
    </div>
  )
}
