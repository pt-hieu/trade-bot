import { useState } from 'react'
import { Card } from './ui/card'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from './ui/dialog'
import { useRiskMetrics } from '../hooks/use-risk-metrics'
import { ErrorState } from './ui/error-state'
import { BetaDialog } from './beta-dialog'

// ── Metric Card ─────────────────────────────────────────────────────────────

interface RiskCardProps {
  label: string
  value: string
  badge?: string
  badgeColor?: string
  variant?: 'default' | 'positive' | 'negative' | 'warning'
  onClick?: () => void
}

const VALUE_COLORS = {
  default: 'text-foreground',
  positive: 'text-emerald-500',
  negative: 'text-rose-500',
  warning: 'text-amber-500',
}

const VARIANT_GRADIENT = { default: undefined, positive: 'positive', negative: 'negative', warning: 'warning' } as const

function RiskCard({ label, value, badge, badgeColor, variant = 'default', onClick }: RiskCardProps) {
  return (
    <Card
      gradient={VARIANT_GRADIENT[variant]}
      className={`border-border/50 py-3 px-4 flex-1 min-w-[120px] ${onClick ? 'cursor-pointer hover:border-border transition-colors' : ''}`}
      onClick={onClick}
      data-test-id={`risk-${label.toLowerCase().replace(/\s+/g, '-')}`}
    >
      <p className={`text-[10px] font-medium tracking-widest text-muted-foreground uppercase truncate ${onClick ? 'underline decoration-dotted underline-offset-2' : ''}`}>
        {label}
      </p>
      <div className="flex items-baseline gap-2">
        <p className={`text-lg font-semibold tracking-tight font-mono tabular-nums ${VALUE_COLORS[variant]}`}>
          {value}
        </p>
        {badge && (
          <span
            className="text-[10px] font-medium tracking-wide"
            style={{ color: badgeColor }}
          >
            {badge}
          </span>
        )}
      </div>
    </Card>
  )
}

// ── Ratio Detail Dialog ─────────────────────────────────────────────────────

function RatioDialog({
  open,
  onOpenChange,
  title,
  description,
  value,
  formula,
  interpretation,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  value: number | null
  formula: string
  interpretation: string
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" onOpenAutoFocus={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col items-center gap-4 py-4">
          <p className="text-4xl font-bold font-mono tabular-nums">
            {value !== null ? value.toFixed(2) : '—'}
          </p>
          <p className="text-xs text-muted-foreground font-mono text-center">{formula}</p>
          <div className="text-xs text-muted-foreground space-y-1 px-2">
            <p>{interpretation}</p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ── Insufficient Data State ─────────────────────────────────────────────────

function AccumulatingData({ current, required }: { current: number; required: number }) {
  const pct = Math.min((current / required) * 100, 100)
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Accumulating data</span>
        <span className="font-mono tabular-nums">{current}/{required} trading days</span>
      </div>
      <div className="h-1.5 rounded-full bg-muted overflow-hidden">
        <div
          className="h-full rounded-full bg-muted-foreground/40 transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

// ── Interpretation helpers ──────────────────────────────────────────────────

function betaInterp(beta: number) {
  if (beta > 1.2) return { badge: 'Aggressive', color: '#f59e0b', variant: 'warning' as const }
  if (beta < 0.8) return { badge: 'Defensive', color: '#38bdf8', variant: 'default' as const }
  return { badge: 'Market', color: '#a1a1aa', variant: 'default' as const }
}

function sharpeInterp(s: number) {
  if (s > 1) return { badge: 'Strong', color: '#10b981', variant: 'positive' as const }
  if (s > 0) return { badge: 'Adequate', color: '#f59e0b', variant: 'warning' as const }
  return { badge: 'Weak', color: '#f43f5e', variant: 'negative' as const }
}

function sortinoInterp(s: number) {
  if (s > 1.5) return { badge: 'Strong', color: '#10b981', variant: 'positive' as const }
  if (s > 0.5) return { badge: 'Adequate', color: '#f59e0b', variant: 'warning' as const }
  return { badge: 'Weak', color: '#f43f5e', variant: 'negative' as const }
}

// ── Main Section ────────────────────────────────────────────────────────────

export function RiskSection() {
  const { data: metrics, isLoading, error, refetch } = useRiskMetrics()
  const [betaOpen, setBetaOpen] = useState(false)
  const [sharpeOpen, setSharpeOpen] = useState(false)
  const [sortinoOpen, setSortinoOpen] = useState(false)

  if (isLoading) {
    return (
      <div className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight">Risk Profile</h2>
        <div className="h-16 flex items-center text-muted-foreground text-sm">Loading risk metrics...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight">Risk Profile</h2>
        <ErrorState description="Could not load risk metrics." retry={refetch} />
      </div>
    )
  }

  if (!metrics) return null

  // Insufficient data state
  if (metrics.message) {
    return (
      <div className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight">Risk Profile</h2>
        <AccumulatingData current={metrics.data_points} required={metrics.minimum_required} />
      </div>
    )
  }

  const beta = metrics.portfolio_beta
  const sharpe = metrics.sharpe_ratio
  const sortino = metrics.sortino_ratio

  const bI = beta !== null ? betaInterp(beta) : null
  const sI = sharpe !== null ? sharpeInterp(sharpe) : null
  const soI = sortino !== null ? sortinoInterp(sortino) : null

  return (
    <div className="space-y-3">
      <div className="flex items-baseline gap-3">
        <h2 className="text-lg font-semibold tracking-tight">Risk Profile</h2>
        <span className="text-xs text-muted-foreground font-mono tabular-nums">
          {metrics.data_points}d rolling
        </span>
      </div>

      <div className="flex gap-3 flex-wrap">
        <RiskCard
          label="Beta"
          value={beta !== null ? beta.toFixed(2) : '—'}
          badge={bI?.badge}
          badgeColor={bI?.color}
          variant={bI?.variant}
          onClick={() => setBetaOpen(true)}
        />
        <RiskCard
          label="Sharpe"
          value={sharpe !== null ? sharpe.toFixed(2) : '—'}
          badge={sI?.badge}
          badgeColor={sI?.color}
          variant={sI?.variant}
          onClick={sharpe !== null ? () => setSharpeOpen(true) : undefined}
        />
        <RiskCard
          label="Sortino"
          value={sortino !== null ? sortino.toFixed(2) : '—'}
          badge={soI?.badge}
          badgeColor={soI?.color}
          variant={soI?.variant}
          onClick={sortino !== null ? () => setSortinoOpen(true) : undefined}
        />
      </div>

      <BetaDialog
        open={betaOpen}
        onOpenChange={setBetaOpen}
        tickerBetas={metrics.ticker_betas}
        portfolioBeta={beta}
      />

      {sharpe !== null && (
        <RatioDialog
          open={sharpeOpen}
          onOpenChange={setSharpeOpen}
          title="Sharpe Ratio"
          description="Risk-adjusted return relative to total volatility"
          value={sharpe}
          formula="(Annualized Return − Risk-Free Rate) / Annualized Volatility"
          interpretation={`Sharpe > 1.0 is good, > 2.0 is excellent. Your portfolio earns ${sharpe.toFixed(2)} units of return per unit of total risk. Risk-free rate: ${(metrics.risk_free_rate * 100).toFixed(0)}% (Vietnam gov bonds).`}
        />
      )}

      {sortino !== null && (
        <RatioDialog
          open={sortinoOpen}
          onOpenChange={setSortinoOpen}
          title="Sortino Ratio"
          description="Risk-adjusted return relative to downside volatility only"
          value={sortino}
          formula="(Annualized Return − Risk-Free Rate) / Downside Deviation"
          interpretation={`Sortino only penalizes negative volatility (bad days). A Sortino > Sharpe means your upside variance is healthy. Your portfolio earns ${sortino.toFixed(2)} units of return per unit of downside risk.`}
        />
      )}
    </div>
  )
}
