import { Card } from '../ui/card'
import { cn, formatCompact } from '../../lib/utils'
import type { PortfolioMetrics } from '../../types/index'

function MetricBox({
  label,
  value,
  subtitle,
  valueColor,
}: {
  label: string
  value: string
  subtitle?: string
  valueColor?: string
}) {
  return (
    <div className="space-y-0.5">
      <p className="text-[10px] text-muted-foreground">{label}</p>
      <p className={cn('text-sm font-semibold font-mono tabular-nums', valueColor)}>{value}</p>
      {subtitle && <p className="text-[10px] text-muted-foreground/60">{subtitle}</p>}
    </div>
  )
}

export function ExposureCard({ metrics }: { metrics: PortfolioMetrics }) {
  const {
    avgDaysHeld,
    longestOpen,
    maxDrawdown,
    systemAlignmentPct,
    systemAlignedCount,
    systemTotalCount,
    portfolioHeatCount,
    portfolioHeatTotal,
    closedWins,
    closedLosses,
    closedWinRate,
    avgWinPct,
    avgLossPct,
    marketValue,
    costBasis,
  } = metrics

  const heatColor = portfolioHeatCount === 0 ? 'text-emerald-400'
    : portfolioHeatCount <= 1 ? 'text-amber-400'
    : 'text-rose-400'

  const drawdownColor = (maxDrawdown?.plPct ?? 0) < -10 ? 'text-rose-400'
    : (maxDrawdown?.plPct ?? 0) < -5 ? 'text-amber-400'
    : 'text-muted-foreground'

  return (
    <Card className="border-border/50 py-4 px-5 gap-4">
      <p className="text-[10px] font-medium tracking-widest text-muted-foreground uppercase">
        Exposure
      </p>

      <div className="grid grid-cols-2 gap-x-6 gap-y-4">
        <MetricBox
          label="Avg days held"
          value={`${avgDaysHeld}d`}
        />
        <MetricBox
          label="Longest open"
          value={longestOpen ? `${longestOpen.days}d` : '—'}
          subtitle={longestOpen ? `${longestOpen.ticker} · ${longestOpen.entryDate.slice(5)}` : undefined}
        />
        <MetricBox
          label="Max drawdown"
          value={maxDrawdown ? `${maxDrawdown.plPct.toFixed(1)}%` : '—'}
          subtitle={maxDrawdown?.ticker}
          valueColor={drawdownColor}
        />
        <MetricBox
          label="System alignment"
          value={`${systemAlignmentPct}%`}
          subtitle={`${systemAlignedCount} of ${systemTotalCount} aligned`}
          valueColor={systemAlignmentPct >= 75 ? 'text-emerald-400' : systemAlignmentPct >= 50 ? 'text-amber-400' : 'text-rose-400'}
        />
        <MetricBox
          label="Portfolio heat"
          value={`${portfolioHeatCount} of ${portfolioHeatTotal} within 5%`}
          valueColor={heatColor}
        />
        <MetricBox
          label="Win rate"
          value={`${closedWinRate}%`}
          subtitle={`${closedWins}W / ${closedLosses}L · avg +${avgWinPct.toFixed(1)}% / ${avgLossPct.toFixed(1)}%`}
          valueColor={closedWinRate >= 50 ? 'text-emerald-400' : 'text-rose-400'}
        />
        <MetricBox
          label="Market value"
          value={formatCompact(marketValue)}
        />
        <MetricBox
          label="Cost basis"
          value={formatCompact(costBasis)}
        />
      </div>

    </Card>
  )
}
