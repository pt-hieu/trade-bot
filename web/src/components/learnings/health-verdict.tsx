import { AlertTriangle, CheckCircle2, XCircle } from 'lucide-react'
import { formatWinRate } from '../../lib/utils'
import type {
  HealthVerdict,
  HealthStatus,
  SubsystemHealth,
  SubsystemName,
  EnrichedLearningsData,
} from '../../types/learnings'

interface Threshold {
  green: number
  amber: number
}

const THRESHOLDS = {
  winRate: { green: 0.55, amber: 0.45 },
  entryHit: { green: 0.40, amber: 0.25 },
  avgPnl: { green: 0, amber: -2 },
  calibrationUnreachable: { green: 30, amber: 50 },
  macroRegime: { green: 0.55, amber: 0.40 },
  rotation: { green: 0.55, amber: 0.40 },
  strategyBest: { green: 0.55, amber: 0.40 },
  tradingModeCompliance: { green: 0.80, amber: 0.60 },
} as const

function classify(value: number | null, threshold: Threshold, lowerIsBetter = false): HealthStatus {
  if (value == null) return 'amber'
  const num = Number(value)
  if (lowerIsBetter) {
    return num <= threshold.green ? 'green' : num <= threshold.amber ? 'amber' : 'red'
  }
  return num >= threshold.green ? 'green' : num >= threshold.amber ? 'amber' : 'red'
}

function subsystem(
  name: SubsystemName,
  status: HealthStatus,
  label: string,
  value: string,
  insufficientData = false,
): SubsystemHealth {
  return { name, status, label, value, insufficientData }
}

export function computeHealthVerdict(data: EnrichedLearningsData): HealthVerdict {
  const subsystems: SubsystemHealth[] = []

  if (data.summary) {
    const winRate = Number(data.summary.overall_win_rate ?? 0)
    subsystems.push(subsystem(
      'win-rate',
      classify(winRate, THRESHOLDS.winRate),
      'Win Rate',
      formatWinRate(winRate),
    ))

    const entryHit = Number(data.summary.overall_entry_hit_rate ?? 0) / 100
    subsystems.push(subsystem(
      'entry-hit',
      classify(entryHit, THRESHOLDS.entryHit),
      'Entry Hit',
      formatWinRate(entryHit),
    ))

    const avgPnl = Number(data.summary.avg_pnl_percent ?? 0)
    subsystems.push(subsystem(
      'avg-pnl',
      classify(avgPnl, THRESHOLDS.avgPnl),
      'Avg P/L',
      `${avgPnl >= 0 ? '+' : ''}${avgPnl.toFixed(1)}%`,
    ))
  }

  if (data.calibration) {
    const unreachable = Number(data.calibration.pct_entries_unreachable ?? 0)
    subsystems.push(subsystem(
      'calibration',
      classify(unreachable, THRESHOLDS.calibrationUnreachable, true),
      'Calibration',
      `${unreachable.toFixed(0)}% unreachable`,
    ))
  }

  if (data.macro) {
    const macroAccuracy = Number(data.macro.overall_accuracy ?? 0)
    subsystems.push(subsystem(
      'macro',
      classify(macroAccuracy, THRESHOLDS.macroRegime),
      'Macro Regime',
      `${formatWinRate(macroAccuracy)} accuracy`,
    ))
  }

  if (data.rotation) {
    const rotationAccuracy = Number(data.rotation.overall_accuracy ?? 0)
    subsystems.push(subsystem(
      'rotation',
      classify(rotationAccuracy, THRESHOLDS.rotation),
      'Sector Rotation',
      `${formatWinRate(rotationAccuracy)} accuracy`,
    ))
  }

  if (data.strategy_insights.length > 0) {
    const qualified = data.strategy_insights.filter(
      (strategy) => (strategy.sample_size ?? 0) >= 5,
    )
    const bestWinRate =
      qualified.length > 0
        ? Math.max(...qualified.map((strategy) => Number(strategy.win_rate ?? 0)))
        : null

    subsystems.push(subsystem(
      'strategy',
      bestWinRate != null ? classify(bestWinRate, THRESHOLDS.strategyBest) : 'amber',
      'Strategy',
      bestWinRate != null ? `best ${formatWinRate(bestWinRate)}` : 'insufficient data',
      bestWinRate == null,
    ))
  }

  if (data.trading_mode) {
    const compliance = Number(data.trading_mode.mode_compliance_rate ?? 0)
    subsystems.push(subsystem(
      'trading-mode',
      classify(compliance, THRESHOLDS.tradingModeCompliance),
      'Trading Mode',
      `${formatWinRate(compliance)} compliance`,
    ))
  }

  const failures = subsystems.filter(
    (entry) => !entry.insufficientData && entry.status !== 'green',
  )
  const unmeasurable = subsystems.filter((entry) => entry.insufficientData)
  const redCount = failures.filter((entry) => entry.status === 'red').length

  const overallStatus: HealthStatus =
    redCount >= 3 ? 'red' : failures.length > 0 ? 'amber' : 'green'

  const parts: string[] = []
  if (failures.length > 0) {
    parts.push(`${failures.length} subsystem${failures.length > 1 ? 's' : ''} failing`)
  }
  if (unmeasurable.length > 0) {
    parts.push(`${unmeasurable.length} unmeasurable`)
  }

  const total = subsystems.length
  const summary =
    failures.length === 0 && unmeasurable.length === 0
      ? `All ${total} subsystems healthy`
      : parts.join(', ')

  return {
    overallStatus,
    summary,
    subsystems,
    failures,
    unmeasurable,
    attentionCount: failures.length + unmeasurable.length,
  }
}

const STATUS_CONFIG: Record<
  HealthStatus,
  { icon: typeof CheckCircle2; containerClass: string; iconClass: string; textClass: string }
> = {
  green: {
    icon: CheckCircle2,
    containerClass: 'bg-emerald-500/8 border-emerald-500/20',
    iconClass: 'text-emerald-400',
    textClass: 'text-emerald-300',
  },
  amber: {
    icon: AlertTriangle,
    containerClass: 'bg-amber-500/8 border-amber-500/20',
    iconClass: 'text-amber-400',
    textClass: 'text-amber-300',
  },
  red: {
    icon: XCircle,
    containerClass: 'bg-rose-500/8 border-rose-500/20',
    iconClass: 'text-rose-400',
    textClass: 'text-rose-300',
  },
}

const DOT_CLASS: Record<HealthStatus, string> = {
  green: 'bg-emerald-400',
  amber: 'bg-amber-400',
  red: 'bg-rose-400',
}

export function HealthVerdictBanner({ verdict }: { verdict: HealthVerdict }) {
  const config = STATUS_CONFIG[verdict.overallStatus]
  const Icon = config.icon

  return (
    <div className={`rounded-lg border px-4 py-3 ${config.containerClass}`}>
      <div className="flex items-center gap-3">
        <Icon className={`h-5 w-5 shrink-0 ${config.iconClass}`} />
        <div className="flex-1 min-w-0">
          <p className={`text-sm font-semibold ${config.textClass}`}>{verdict.summary}</p>
          {(verdict.failures.length > 0 || verdict.unmeasurable.length > 0) && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1.5">
              {verdict.failures.map((entry) => (
                <span
                  key={entry.name}
                  className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${DOT_CLASS[entry.status]}`} />
                  {entry.label}: {entry.value}
                </span>
              ))}
              {verdict.unmeasurable.length > 0 && verdict.failures.length > 0 && (
                <span className="text-xs text-muted-foreground/40">·</span>
              )}
              {verdict.unmeasurable.map((entry) => (
                <span
                  key={entry.name}
                  className="inline-flex items-center gap-1.5 text-xs text-muted-foreground/50 italic"
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/30" />
                  {entry.label}: {entry.value}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function HealthDot({ status }: { status: HealthStatus }) {
  return <span className={`h-2 w-2 rounded-full shrink-0 ${DOT_CLASS[status]}`} />
}
