import { useState } from 'react'
import { Card } from './ui/card'
import { useSwingMetrics } from '../hooks/use-metrics'
import { formatCompact } from '../lib/utils'
import { ErrorState } from './ui/error-state'
import { WinRateDialog } from './metrics/win-rate-dialog'
import { ProfitFactorDialog } from './metrics/profit-factor-dialog'
import { ExpectancyCurveDialog } from './metrics/expectancy-curve-dialog'

interface MetricCardProps {
  label: string
  value: string
  variant?: 'default' | 'positive' | 'negative' | 'warning'
  onClick?: () => void
}

const VARIANT_GRADIENT = { default: undefined, positive: 'positive', negative: 'negative', warning: 'warning' } as const

function MetricCard({ label, value, variant = 'default', onClick }: MetricCardProps) {
  const valueColor = {
    default: 'text-foreground',
    positive: 'text-emerald-500',
    negative: 'text-rose-500',
    warning: 'text-amber-500',
  }[variant]

  return (
    <Card
      gradient={VARIANT_GRADIENT[variant]}
      className={`border-border/50 py-3 px-4 flex-1 min-w-[120px] ${onClick ? 'cursor-pointer hover:border-border transition-colors' : ''}`}
      onClick={onClick}
      data-test-id={`metric-${label.toLowerCase().replace(/\s+/g, '-')}`}
    >
      <p className={`text-[10px] font-medium tracking-widest text-muted-foreground uppercase truncate ${onClick ? 'underline decoration-dotted underline-offset-2' : ''}`}>
        {label}
      </p>
      <p className={`text-lg font-semibold tracking-tight font-mono tabular-nums ${valueColor}`}>
        {value}
      </p>
    </Card>
  )
}

export function MetricsSection() {
  const { data: metrics, isLoading, error, refetch } = useSwingMetrics()
  const [winRateOpen, setWinRateOpen] = useState(false)
  const [profitFactorOpen, setProfitFactorOpen] = useState(false)
  const [expectancyOpen, setExpectancyOpen] = useState(false)

  if (isLoading) {
    return (
      <div className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight">Performance</h2>
        <div className="h-16 flex items-center text-muted-foreground text-sm">
          Loading metrics...
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight">Performance</h2>
        <ErrorState description="Could not load performance metrics. Metrics require at least one closed trade." retry={refetch} />
      </div>
    )
  }

  if (!metrics) {
    return (
      <div className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight">Performance</h2>
        <div className="text-muted-foreground text-sm">No metrics available</div>
      </div>
    )
  }

  const m = metrics as any
  const winRateVariant = Number(m.win_rate) >= 50 ? 'positive' : 'negative'

  let profitFactorVariant: MetricCardProps['variant'] = 'default'
  if (m.profit_factor !== null) {
    if (Number(m.profit_factor) >= 1.5) profitFactorVariant = 'positive'
    else if (Number(m.profit_factor) >= 1.0) profitFactorVariant = 'warning'
    else profitFactorVariant = 'negative'
  }

  const expectancyVariant: MetricCardProps['variant'] =
    m.expectancy_vnd === null ? 'default' : Number(m.expectancy_vnd) >= 0 ? 'positive' : 'negative'

  return (
    <div className="space-y-3">
      <h2 className="text-lg font-semibold tracking-tight">Performance</h2>
      <div className="flex gap-3 flex-wrap">
        <MetricCard
          label="Trades"
          value={`${m.total_trades}`}
        />
        <MetricCard
          label="Win Rate"
          value={`${m.win_rate}%`}
          variant={winRateVariant}
          onClick={() => setWinRateOpen(true)}
        />
        <MetricCard
          label="Profit Factor"
          value={m.profit_factor !== null ? Number(m.profit_factor).toFixed(2) : '-'}
          variant={profitFactorVariant}
          onClick={m.profit_factor !== null ? () => setProfitFactorOpen(true) : undefined}
        />
        <MetricCard
          label="Expectancy"
          value={
            m.expectancy_vnd !== null
              ? `${Number(m.expectancy_vnd) >= 0 ? '+' : ''}${formatCompact(m.expectancy_vnd)}`
              : '-'
          }
          variant={expectancyVariant}
          onClick={
            m.avg_win_vnd !== null && m.avg_loss_vnd !== null
              ? () => setExpectancyOpen(true)
              : undefined
          }
        />
        <MetricCard
          label="Avg Hold"
          value={m.avg_holding_days !== null ? `${m.avg_holding_days}d` : '-'}
        />
        <MetricCard
          label="Max Win"
          value={m.max_win_vnd !== null ? `+${formatCompact(m.max_win_vnd)}` : '-'}
          variant="positive"
        />
        <MetricCard
          label="Max Loss"
          value={m.max_loss_vnd !== null ? formatCompact(m.max_loss_vnd) : '-'}
          variant="negative"
        />
      </div>

      <WinRateDialog
        open={winRateOpen}
        onOpenChange={setWinRateOpen}
        wins={m.wins}
        losses={m.losses}
        winRate={Number(m.win_rate)}
      />
      {m.profit_factor !== null && (
        <ProfitFactorDialog
          open={profitFactorOpen}
          onOpenChange={setProfitFactorOpen}
          grossProfit={Number(m.avg_win_vnd ?? 0) * Number(m.wins)}
          grossLoss={Math.abs(Number(m.avg_loss_vnd ?? 0)) * Number(m.losses)}
          profitFactor={Number(m.profit_factor)}
        />
      )}
      {m.avg_win_vnd !== null && m.avg_loss_vnd !== null && (
        <ExpectancyCurveDialog
          open={expectancyOpen}
          onOpenChange={setExpectancyOpen}
          winRate={Number(m.win_rate)}
          winLossRatio={Math.abs(Number(m.avg_win_vnd)) / Math.abs(Number(m.avg_loss_vnd))}
          expectancyVnd={Number(m.expectancy_vnd ?? 0)}
        />
      )}
    </div>
  )
}
