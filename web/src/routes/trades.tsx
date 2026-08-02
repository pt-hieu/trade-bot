import { createFileRoute, useSearch, useNavigate } from '@tanstack/react-router'
import { useState, useMemo } from 'react'
import { Plus, X } from 'lucide-react'
import { Button } from '../components/ui/button'
import { ConfirmDialog } from '../components/ui/confirm-dialog'
import { ErrorState } from '../components/ui/error-state'
import { TickerPositionCard } from '../components/trades/ticker-position-card'
import { TickerHistoryRow } from '../components/trades/ticker-history-row'
import { StrategyFilterBar } from '../components/trades/strategy-filter-bar'
import { TradeSheet } from '../components/trades/trade-sheet'
import { useAllTrades, useDeleteTrade } from '../hooks/use-trades'
import { useEnhancedHoldings } from '../hooks/use-portfolio'
import { groupTradesByTicker, filterGroups } from '../lib/trade-grouping'
import { formatSignedCompact, plColor } from '../lib/utils'
import { formatShortDate } from '../lib/date'
import type { Strategy } from '../lib/strategy'
import type { Trade, EnhancedHolding } from '../types/index'

export const Route = createFileRoute('/trades')({
  validateSearch: (search: Record<string, unknown>) => ({
    strategy: (search.strategy as string) ?? undefined,
    ticker: (search.ticker as string) ?? undefined,
  }),
  component: TradesPage,
  ssr: false,
})

function TradesPage() {
  const navigate = useNavigate()
  const search = useSearch({ from: '/trades' })
  const strategyFilter = search.strategy
  const tickerFilter = search.ticker

  const { data: tradesRaw, isLoading, error, refetch } = useAllTrades()
  const trades = tradesRaw as Trade[] | undefined
  const { data: enhancedHoldings } = useEnhancedHoldings()
  const deleteTrade = useDeleteTrade()

  const currentPrices = useMemo(() => {
    const priceMap = new Map<string, number>()
    if (!enhancedHoldings) return priceMap
    for (const holding of enhancedHoldings as EnhancedHolding[]) {
      if (holding.ticker && holding.currentPriceVnd) {
        priceMap.set(holding.ticker, Number(holding.currentPriceVnd))
      }
    }
    return priceMap
  }, [enhancedHoldings])

  // Group once, filter without re-grouping
  const allGrouped = useMemo(
    () => groupTradesByTicker(trades || []),
    [trades]
  )

  const { openGroups, closedGroups, maxAbsolutePlVnd } = useMemo(
    () => filterGroups(allGrouped, strategyFilter, tickerFilter),
    [allGrouped, strategyFilter, tickerFilter]
  )

  const allTickerGroups = useMemo(
    () => [...allGrouped.openGroups, ...allGrouped.closedGroups],
    [allGrouped]
  )

  // Sheet state
  const [sheetOpen, setSheetOpen] = useState(false)
  const [selectedTrade, setSelectedTrade] = useState<Trade | undefined>()
  const [initialStatus, setInitialStatus] = useState<'OPEN' | 'CLOSED' | undefined>()
  const [deleteTarget, setDeleteTarget] = useState<Trade | null>(null)

  const handleNewTrade = () => {
    setSelectedTrade(undefined)
    setInitialStatus(undefined)
    setSheetOpen(true)
  }

  const handleEditTrade = (trade: Trade) => {
    setSelectedTrade(trade)
    setInitialStatus(undefined)
    setSheetOpen(true)
  }

  const handleCloseTrade = (trade: Trade) => {
    setSelectedTrade(trade)
    setInitialStatus('CLOSED')
    setSheetOpen(true)
  }

  const setStrategy = (strategy: Strategy | null) => {
    navigate({
      to: '/trades',
      search: (previous: any) => ({ ...previous, strategy: strategy ?? undefined }),
      replace: true,
    } as any)
  }

  const clearTicker = () => {
    navigate({
      to: '/trades',
      search: (previous: any) => {
        const { ticker: _removed, ...rest } = previous
        return rest
      },
      replace: true,
    } as any)
  }

  const totalOpenPositions = openGroups.length
  const totalRealizedPl = useMemo(
    () =>
      [...allGrouped.openGroups, ...allGrouped.closedGroups].reduce(
        (sum, group) => sum + group.netPlVnd,
        0
      ),
    [allGrouped]
  )

  return (
    <main className="min-h-[calc(100dvh-77px)] p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Trades</h1>
          {!isLoading && trades && (
            <p className="text-sm text-muted-foreground mt-0.5">
              {totalOpenPositions} open position{totalOpenPositions !== 1 ? 's' : ''} ·{' '}
              <span className={plColor(totalRealizedPl)}>
                {formatSignedCompact(totalRealizedPl)} realized
              </span>
            </p>
          )}
        </div>
        <Button onClick={handleNewTrade} size="sm" data-test-id="new-trade-btn">
          <Plus className="h-4 w-4 mr-1" />
          New Trade
        </Button>
      </div>

      {tickerFilter && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Filtered to</span>
          <button
            onClick={clearTicker}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-foreground/10 text-foreground border border-foreground/20 cursor-pointer hover:bg-foreground/15 transition-colors"
          >
            {tickerFilter.toUpperCase()}
            <X className="h-3 w-3" />
          </button>
        </div>
      )}

      <StrategyFilterBar
        activeStrategy={strategyFilter}
        onStrategyChange={setStrategy}
        strategyCounts={allGrouped.strategyCounts}
        totalCount={trades?.length || 0}
      />

      {isLoading ? (
        <LoadingSkeleton />
      ) : error ? (
        <ErrorState description="Could not load trade history." retry={refetch} />
      ) : !trades?.length ? (
        <div className="text-muted-foreground py-12 text-center">
          Record your first trade to start tracking performance.
        </div>
      ) : openGroups.length === 0 && closedGroups.length === 0 ? (
        <div className="text-muted-foreground py-12 text-center">
          No {strategyFilter ? `${strategyFilter} ` : ''}
          {tickerFilter ? `${tickerFilter.toUpperCase()} ` : ''}trades match.
          <span className="block mt-1 text-sm">
            Try clearing filters to see all trades.
          </span>
        </div>
      ) : (
        <div className="space-y-8">
          {openGroups.length > 0 && (
            <section>
              <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide mb-3">
                Open Positions
                <span className="ml-2 text-foreground">{openGroups.length}</span>
              </h2>
              <div className="space-y-2">
                {openGroups.map((group) => (
                  <TickerPositionCard
                    key={group.ticker}
                    group={group}
                    currentPriceVnd={currentPrices.get(group.ticker)}
                    onEditTrade={handleEditTrade}
                    onCloseTrade={handleCloseTrade}
                  />
                ))}
              </div>
            </section>
          )}

          {closedGroups.length > 0 && (
            <section>
              <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide mb-3">
                Trade History
                <span className="ml-2 text-foreground">{closedGroups.length}</span>
              </h2>
              <div className="space-y-1.5">
                {closedGroups.map((group) => (
                  <TickerHistoryRow
                    key={group.ticker}
                    group={group}
                    maxAbsolutePlVnd={maxAbsolutePlVnd}
                    onEditTrade={handleEditTrade}
                    onDeleteTrade={(trade) => setDeleteTarget(trade)}
                  />
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      <TradeSheet
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        trade={selectedTrade}
        initialStatus={initialStatus}
        tickerGroups={allTickerGroups}
        currentPrices={currentPrices}
      />

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null) }}
        title="Delete Trade"
        description={`Delete ${deleteTarget?.ticker} trade from ${deleteTarget?.entry_date ? formatShortDate(deleteTarget.entry_date) : '—'}? This cannot be undone.`}
        confirmText="Delete"
        variant="destructive"
        onConfirm={async () => {
          if (!deleteTarget) return
          await deleteTrade.mutateAsync(deleteTarget.id)
          setDeleteTarget(null)
        }}
        isPending={deleteTrade.isPending}
      />
    </main>
  )
}

function LoadingSkeleton() {
  return (
    <div className="space-y-2">
      {[1, 2, 3].map((index) => (
        <div key={index} className="h-16 rounded-lg border bg-card animate-pulse" />
      ))}
    </div>
  )
}
