import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useState, useMemo } from 'react'
import { Radio } from 'lucide-react'
import { IntelSummary } from '../components/intel-summary'
import { CommandStat } from '../components/war-room/command-stat'
import { AlertsPanel } from '../components/war-room/alerts-panel'
import { PositionsPanel } from '../components/war-room/positions-panel'
import { OpenTradesPanel } from '../components/war-room/open-trades-panel'
import { WatchlistRadar } from '../components/war-room/watchlist-radar'
import { ForeignFlowMini } from '../components/war-room/foreign-flow-mini'
import { StrategyWinRate } from '../components/war-room/strategy-winrate'
import { NewsMini } from '../components/war-room/news-mini'
import { NarrativesMini } from '../components/war-room/narratives-mini'
import { CashDialog } from '../components/cash-dialog'
import { ChartDialog } from '../components/chart/chart-dialog'
import { usePortfolio } from '../hooks/use-portfolio'
import { useSwingMetrics } from '../hooks/use-metrics'
import { useGoals } from '../hooks/use-goals'
import { useDailyIntel } from '../hooks/use-intel'
import { useMarketStream } from '../hooks/use-market-stream'
import { cn, formatCompact, formatPct } from '../lib/utils'

export const Route = createFileRoute('/')({
  component: HomePage,
  ssr: false,
})

function nearestActiveGoal(goals: ReturnType<typeof useGoals>['data']) {
  if (!goals) return null
  const active = goals.filter((g) => g.status === 'Active' || g.status === 'Tracking')
  if (active.length === 0) return null
  return active.sort(
    (a, b) => new Date(a.deadline).getTime() - new Date(b.deadline).getTime()
  )[0]
}

function HomePage() {
  const navigate = useNavigate()
  const [cashOpen, setCashOpen] = useState(false)
  const [chartTicker, setChartTicker] = useState<string | null>(null)

  const { data: holdings, isLoading: holdingsLoading } = usePortfolio()
  const { data: metricsRaw, isLoading: metricsLoading } = useSwingMetrics()
  const metrics = metricsRaw as any
  const { data: goals, isLoading: goalsLoading } = useGoals()
  const { data: intel, isLoading: intelLoading } = useDailyIntel()

  const streamTickers = useMemo(
    () => holdings?.filter((h) => h.holding_type !== 'Cash').map((h) => h.ticker) ?? [],
    [holdings]
  )
  const { prices: livePrices, isConnected: streamConnected } = useMarketStream(streamTickers)

  const cashHolding = holdings?.find((h) => h.holding_type === 'Cash')
  const cashValue = cashHolding ? Number(cashHolding.market_value_vnd) : null

  const positions = useMemo(
    () => holdings?.filter((h) => h.holding_type !== 'Cash') ?? [],
    [holdings]
  )

  const totalPl = useMemo(
    () =>
      positions.reduce((sum, h) => {
        const live = livePrices.get(h.ticker)
        const pl = live
          ? (live.price - Number(h.avg_cost_vnd)) * Number(h.shares)
          : Number(h.pl_vnd)
        return sum + pl
      }, 0),
    [positions, livePrices]
  )

  const totalPlPct = useMemo(() => {
    const totalCostBasis = positions.reduce((sum, h) => sum + Number(h.cost_basis_vnd), 0)
    return totalCostBasis > 0 ? (totalPl / totalCostBasis) * 100 : null
  }, [positions, totalPl])

  const goal = nearestActiveGoal(goals)
  const goalPct = goal && Number(goal.target_vnd) > 0
    ? Math.min(100, (Number(goal.realized_vnd) / Number(goal.target_vnd)) * 100)
    : null
  const daysLeft = goal
    ? Math.ceil((new Date(goal.deadline).getTime() - Date.now()) / 86_400_000)
    : null

  return (
    <main className="min-h-[calc(100dvh-77px)] p-4 max-w-7xl mx-auto space-y-3">
      {/* Row 1: Regime strip */}
      <IntelSummary />

      {/* Row 2: Command bar */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <CommandStat
          label="Deployable cash"
          value={cashValue != null ? formatCompact(cashValue) : null}
          gradient="none"
          onClick={() => setCashOpen(true)}
          isLoading={holdingsLoading}
          data-test-id="command-stat-cash"
        />
        <CommandStat
          label="Portfolio P/L"
          value={totalPl !== 0 ? `${totalPl >= 0 ? '+' : ''}${formatCompact(totalPl)}` : '—'}
          subtitle={totalPlPct != null ? formatPct(totalPlPct) : undefined}
          gradient={totalPl > 0 ? 'positive' : totalPl < 0 ? 'negative' : 'none'}
          onClick={() => navigate({ to: '/portfolio' })}
          isLoading={holdingsLoading}
          data-test-id="command-stat-pl"
        />
        <CommandStat
          label="Win rate"
          value={metrics ? `${Number(metrics.win_rate).toFixed(1)}%` : null}
          subtitle={metrics ? `${metrics.wins}W / ${metrics.losses}L` : undefined}
          gradient={
            metrics
              ? Number(metrics.win_rate) >= 50
                ? 'positive'
                : 'negative'
              : 'none'
          }
          onClick={() => navigate({ to: '/trades', search: {} as any })}
          isLoading={metricsLoading}
          data-test-id="command-stat-winrate"
        />
        <CommandStat
          label="Goal progress"
          value={goalPct != null ? `${goalPct.toFixed(0)}%` : null}
          subtitle={
            goal
              ? daysLeft != null && daysLeft > 0
                ? `${goal.name} · ${daysLeft}d left`
                : goal.name
              : 'No active goal'
          }
          gradient={
            goalPct == null
              ? 'none'
              : goalPct >= 80
                ? 'positive'
                : goalPct >= 50
                  ? 'warning'
                  : 'negative'
          }
          onClick={() => navigate({ to: '/goals' })}
          isLoading={goalsLoading}
          data-test-id="command-stat-goal"
        />
      </div>

      {/* Row 3: Open trades + Positions */}
      <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-3">
        <OpenTradesPanel onTickerClick={setChartTicker} />
        <PositionsPanel onTickerClick={setChartTicker} />
      </div>

      {/* Row 4: Alerts + Watchlist radar */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <AlertsPanel onTickerClick={setChartTicker} />
        <WatchlistRadar onTickerClick={setChartTicker} />
      </div>

      {/* Row 5: Intel strip */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        <ForeignFlowMini flow={intel?.foreign_flow} isLoading={intelLoading} />
        <StrategyWinRate />
        <NewsMini articles={(intel as any)?.articles} isLoading={intelLoading} />
        <NarrativesMini />
      </div>

      {/* Footer: stream status */}
      <div className="flex items-center text-[10px] text-muted-foreground px-1">
        <div className="flex items-center gap-1.5">
          <Radio
            className={cn(
              'h-2.5 w-2.5',
              streamConnected ? 'text-emerald-500 animate-pulse' : 'text-muted-foreground/40'
            )}
          />
          <span>{streamConnected ? 'Live stream' : 'Polling mode'}</span>
        </div>
      </div>

      <CashDialog
        open={cashOpen}
        onOpenChange={setCashOpen}
        currentBalance={cashValue ?? 0}
      />
      <ChartDialog
        ticker={chartTicker}
        open={!!chartTicker}
        onOpenChange={(open) => { if (!open) setChartTicker(null) }}
      />
    </main>
  )
}
