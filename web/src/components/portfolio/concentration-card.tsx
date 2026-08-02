import { AlertTriangle } from 'lucide-react'
import { Card } from '../ui/card'
import { toTitleCase } from '../../lib/utils'
import type { PortfolioMetrics, PositionSizingViolation } from '../../types/index'

export function PositionViolationsList({ violations }: { violations: PositionSizingViolation[] }) {
  if (violations.length === 0) return null
  return (
    <div className="space-y-1">
      {violations.map((violation) => (
        <div key={violation.ticker} className="flex items-center gap-1.5 text-xs text-amber-400">
          <AlertTriangle className="h-3 w-3 shrink-0" />
          <span>
            {violation.ticker}: {violation.weightPct.toFixed(1)}% — exceeds {violation.limitPct}% single-name limit
          </span>
        </div>
      ))}
    </div>
  )
}

const SECTOR_BAR_COLORS: Record<string, string> = {
  technology: 'bg-violet-500',
  banking: 'bg-blue-500',
  real_estate: 'bg-amber-500',
  consumer: 'bg-emerald-500',
  infrastructure: 'bg-cyan-500',
  state_owned: 'bg-rose-500',
}

export function ConcentrationCard({ metrics }: { metrics: PortfolioMetrics }) {
  const { sectors, herfindahlIndex, concentrationLabel, positionViolations } = metrics

  const concentrationColor = concentrationLabel === 'Concentrated'
    ? 'text-rose-400'
    : concentrationLabel === 'Moderate'
    ? 'text-amber-400'
    : 'text-emerald-400'

  return (
    <Card className="border-border/50 py-4 px-5 gap-4">
      <p className="text-[10px] font-medium tracking-widest text-muted-foreground uppercase">
        Sector concentration
      </p>

      <div className="space-y-2.5">
        {sectors.map((sector) => {
          const barColor = SECTOR_BAR_COLORS[sector.sectorName] || 'bg-indigo-500'
          return (
            <div key={sector.sectorName} className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground w-24 shrink-0">
                {toTitleCase(sector.sectorName)}
              </span>
              <div className="flex-1 h-2 bg-muted/30 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${barColor}`}
                  style={{ width: `${Math.min(sector.weightPct, 100)}%` }}
                />
              </div>
              <span className="text-xs font-mono tabular-nums text-muted-foreground w-12 text-right">
                {sector.weightPct.toFixed(1)}%
              </span>
            </div>
          )
        })}
      </div>

      <div className="flex items-center justify-between pt-1 border-t border-border/30">
        <span className="text-xs text-muted-foreground">
          HHI: <span className="font-mono tabular-nums">{herfindahlIndex.toLocaleString()}</span>
        </span>
        <span className={`text-xs font-medium ${concentrationColor}`}>
          {concentrationLabel}
        </span>
      </div>

      <PositionViolationsList violations={positionViolations} />
    </Card>
  )
}
