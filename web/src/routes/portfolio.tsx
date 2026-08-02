import { createFileRoute } from '@tanstack/react-router'
import { useState, useMemo } from 'react'
import {
  usePortfolioSummary,
  usePortfolioHistory,
  useEnhancedHoldings,
  usePortfolioMetrics,
  useHoldingsAt,
} from '../hooks/use-portfolio'
import { useCatalysts, useCapitalEvents } from '../hooks/use-catalysts'
import { useNarratives } from '../hooks/use-narratives'
import type { TickerContext } from '../types/index'
import { ErrorState } from '../components/ui/error-state'
import { Skeleton } from '../components/ui/skeleton'
import { formatShortDate } from '../lib/date'
import { SummaryStrip, SummaryStripSkeleton } from '../components/portfolio/summary-strip'
import { ValueChart } from '../components/portfolio/value-chart'
import { ReturnStrip } from '../components/portfolio/return-strip'
import { EnhancedHoldingsTable, EnhancedHoldingsSkeleton } from '../components/portfolio/enhanced-holdings'
import { ConcentrationCard } from '../components/portfolio/concentration-card'
import { ExposureCard } from '../components/portfolio/exposure-card'
import { DateHoldingsTable } from '../components/portfolio/date-holdings-table'
import type { TimeRange } from '../components/portfolio/chart-alpha'

export const Route = createFileRoute('/portfolio')({
  component: PortfolioPage,
  ssr: false,
})

function PortfolioPage() {
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [timeRange, setTimeRange] = useState<TimeRange>('ALL')

  const { data: summary, isLoading: summaryLoading, error: summaryError } = usePortfolioSummary()
  const { data: historyData, isLoading: historyLoading, error: historyError } = usePortfolioHistory()
  const { data: enhancedHoldings, isLoading: holdingsLoading, error: holdingsError } = useEnhancedHoldings()
  const { data: metrics, isLoading: metricsLoading, error: metricsError } = usePortfolioMetrics()
  const { data: dateHoldings, isFetching: dateHoldingsFetching } = useHoldingsAt(selectedDate)
  const { data: catalysts } = useCatalysts()
  const { data: narratives } = useNarratives({ status: 'active' })
  const { data: capitalEvents } = useCapitalEvents()

  const tickerContextMap = useMemo(() => {
    const map = new Map<string, TickerContext>()
    if (!enhancedHoldings) return map

    const holdingTickers = new Set(enhancedHoldings.map((holding) => holding.ticker))

    for (const ticker of holdingTickers) {
      const tickerCatalysts = (catalysts ?? []).filter(
        (catalyst) => catalyst.affected_tickers?.includes(ticker) && catalyst.status !== 'expired' && catalyst.status !== 'resolved'
      )
      const tickerNarratives = (narratives ?? []).filter(
        (narrative) => narrative.affected_tickers?.includes(ticker)
      )
      const tickerCapitalEvents = (capitalEvents ?? []).filter(
        (event) => event.ticker === ticker && event.status === 'pending'
      )

      const total = tickerCatalysts.length + tickerNarratives.length + tickerCapitalEvents.length
      if (total > 0) {
        map.set(ticker, {
          catalystCount: tickerCatalysts.length,
          narrativeCount: tickerNarratives.length,
          capitalEventCount: tickerCapitalEvents.length,
          hasNegative: tickerCatalysts.some((catalyst) => catalyst.impact === 'NEGATIVE')
            || tickerCapitalEvents.some((event) => event.impact.startsWith('NEGATIVE')),
        })
      }
    }
    return map
  }, [enhancedHoldings, catalysts, narratives, capitalEvents])

  const error = summaryError || historyError || holdingsError || metricsError

  return (
    <main className="min-h-[calc(100dvh-77px)] p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Portfolio</h1>
        {summary?.lastUpdated && (
          <span className="text-xs text-muted-foreground">
            Updated {formatShortDate(summary.lastUpdated)}
          </span>
        )}
      </div>

      {error && <ErrorState description="Could not load portfolio data." />}

      {summaryLoading ? <SummaryStripSkeleton /> : summary ? <SummaryStrip summary={summary} /> : null}

      {historyLoading ? (
        <Skeleton className="h-[400px] w-full" />
      ) : historyData && historyData.snapshots.length > 0 ? (
        <div className="space-y-2">
          <ValueChart
            snapshots={historyData.snapshots}
            trades={historyData.trades ?? []}
            costBasis={summary?.costBasis}
            onDateSelect={setSelectedDate}
            timeRange={timeRange}
            onTimeRangeChange={setTimeRange}
          />
          <ReturnStrip
            snapshots={historyData.snapshots}
            vnindex={historyData.vnindex ?? []}
            timeRange={timeRange}
          />
        </div>
      ) : null}

      {selectedDate ? (
        <div>
          <div className="flex items-center gap-3 mb-3">
            <p className="text-[10px] font-medium tracking-widest text-muted-foreground uppercase">
              Holdings on {formatShortDate(selectedDate)}
            </p>
            <button
              onClick={() => setSelectedDate(null)}
              className="text-[10px] font-medium tracking-widest uppercase text-muted-foreground hover:text-foreground transition-colors underline cursor-pointer"
            >
              Clear
            </button>
          </div>
          {dateHoldingsFetching ? (
            <Skeleton className="h-[120px] w-full" />
          ) : dateHoldings && dateHoldings.length > 0 ? (
            <DateHoldingsTable holdings={dateHoldings} />
          ) : (
            <p className="text-sm text-muted-foreground py-4">No holdings on this date</p>
          )}
        </div>
      ) : holdingsLoading ? (
        <EnhancedHoldingsSkeleton />
      ) : enhancedHoldings && enhancedHoldings.length > 0 ? (
        <EnhancedHoldingsTable holdings={enhancedHoldings} tickerContext={tickerContextMap} />
      ) : null}

      {metricsLoading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Skeleton className="h-[200px]" />
          <Skeleton className="h-[200px]" />
        </div>
      ) : metrics ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <ConcentrationCard metrics={metrics} />
          <ExposureCard metrics={metrics} />
        </div>
      ) : null}
    </main>
  )
}
