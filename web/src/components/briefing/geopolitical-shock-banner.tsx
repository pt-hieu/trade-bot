import { AlertTriangle } from 'lucide-react'
import { InsightToggle, InsightTrigger, InsightCard } from '../ui/detail-text'
import type { GeopoliticalShockData, ShockPhase } from '../../types/index'
import type { MacroData, RegimeData } from '../../types/intel'

// ── Severity levels ──────────────────────────────────────────────────────────

type SeverityLevel = 'critical' | 'elevated' | 'moderate'

interface PhaseVisuals {
  label: string
  gradient: string
  border: string
  badge: string
  dot?: string
  container: string
  iconSize: string
  textSize: string
}

/** Phase is the pipeline's classification. Severity is the composite read of regime + macro context. */
function computeSeverity(
  phase: ShockPhase,
  regime: RegimeData | null | undefined,
  macro: MacroData | null | undefined,
): SeverityLevel {
  // immediate_shock is always critical
  if (phase === 'immediate_shock') return 'critical'

  // Count stress signals from macro context
  let stressSignals = 0
  if (regime?.regime === 'RISK_OFF') stressSignals++
  if (macro?.global_risk_regime === 'CRISIS') stressSignals += 2
  else if (macro?.global_risk_regime === 'ELEVATED') stressSignals++
  if (macro?.vix_signal === 'EXTREME') stressSignals += 2
  else if (macro?.vix_signal === 'HIGH') stressSignals++
  if (macro?.dxy_signal === 'STRONG') stressSignals++
  if (macro?.usd_vnd_signal === 'FLIGHT') stressSignals++

  // sustained_pressure with heavy stress context → escalate to critical
  if (phase === 'sustained_pressure' && stressSignals >= 3) return 'critical'
  if (phase === 'sustained_pressure' && stressSignals >= 1) return 'elevated'

  // resolution_or_escalation with stress → elevated
  if (phase === 'resolution_or_escalation' && stressSignals >= 2) return 'elevated'

  return 'moderate'
}

// ── Visual config by severity level ──────────────────────────────────────────

const PHASE_LABELS: Record<ShockPhase, string> = {
  immediate_shock: 'IMMEDIATE SHOCK',
  sustained_pressure: 'SUSTAINED PRESSURE',
  resolution_or_escalation: 'RESOLUTION / ESCALATION',
}

const SEVERITY_VISUALS: Record<SeverityLevel, Omit<PhaseVisuals, 'label'>> = {
  critical: {
    gradient: 'from-rose-500/20 via-rose-500/5 to-transparent',
    border: 'border-rose-500/40',
    badge: 'bg-rose-500/25 text-rose-300',
    dot: 'animate-pulse',
    container: 'rounded-xl',
    iconSize: 'w-6 h-6',
    textSize: 'text-base',
  },
  elevated: {
    gradient: 'from-orange-500/15 via-orange-500/5 to-transparent',
    border: 'border-orange-500/35',
    badge: 'bg-orange-500/25 text-orange-300',
    dot: 'animate-pulse',
    container: 'rounded-xl',
    iconSize: 'w-5 h-5',
    textSize: 'text-sm',
  },
  moderate: {
    gradient: 'from-amber-500/6 via-transparent to-transparent',
    border: 'border-amber-500/20',
    badge: 'bg-amber-500/20 text-amber-400',
    container: 'rounded-xl',
    iconSize: 'w-5 h-5',
    textSize: 'text-sm',
  },
}

// ── Ticker grouping ──────────────────────────────────────────────────────────

interface TickerGroups {
  pain: string[]
  benefit: string[]
}

function parseTickerGroups(notes: string, allTickers: string[]): TickerGroups {
  const lower = notes.toLowerCase()

  // Extract benefit tickers from "Defensive: energy (GAS, PVD, PVS) may benefit" pattern
  const benefitMatch = lower.match(/(?:benefit|defensive|hedge)[^.]*?\(([^)]+)\)/i)
  const benefitTickers = benefitMatch
    ? benefitMatch[1].split(',').map(t => t.trim().toUpperCase())
    : []

  const benefitSet = new Set(benefitTickers)
  const pain = allTickers.filter(t => !benefitSet.has(t))
  const benefit = allTickers.filter(t => benefitSet.has(t))

  return { pain, benefit }
}

// ── Component ────────────────────────────────────────────────────────────────

interface GeopoliticalShockBannerProps {
  shock: GeopoliticalShockData
  /** Pass regime + macro for severity-aware escalation */
  regime?: RegimeData | null
  macro?: MacroData | null
}

export function GeopoliticalShockBanner({ shock, regime, macro }: GeopoliticalShockBannerProps) {
  const severity = computeSeverity(shock.phase_name, regime, macro)
  const visuals = SEVERITY_VISUALS[severity]
  const label = PHASE_LABELS[shock.phase_name]
  const { pain, benefit } = parseTickerGroups(shock.notes, shock.affected_tickers)

  return (
    <InsightToggle>
      <div
        className="animate-in fade-in slide-in-from-bottom-2 duration-500"
        style={{ animationDelay: '30ms' }}
        data-test-id="geopolitical-shock-banner"
      >
        <div className={`${visuals.container} border ${visuals.border} bg-gradient-to-r ${visuals.gradient} p-4 space-y-3`}>
          {/* Header: icon + phase + catalyst */}
          <div className="flex items-start gap-3">
            <div className="mt-0.5 shrink-0">
              <AlertTriangle className={`${visuals.iconSize} text-rose-400`} />
            </div>
            <div className="flex-1 min-w-0 space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-bold tracking-widest ${visuals.badge}`}>
                  {visuals.dot && (
                    <span className={`w-1.5 h-1.5 rounded-full bg-current ${visuals.dot}`} />
                  )}
                  {label}
                </span>
                <InsightTrigger />
              </div>
              <p className={`${visuals.textSize} font-medium leading-snug`}>
                {shock.catalyst_event}
              </p>
            </div>
          </div>

          {/* Affected tickers */}
          {(pain.length > 0 || benefit.length > 0) && (
            <div className="flex flex-wrap gap-x-4 gap-y-2 pl-8">
              {pain.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-xs font-medium tracking-wide text-rose-500 uppercase">Pain</span>
                  {pain.map(t => (
                    <span key={t} className="px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-400 text-xs font-mono font-medium">
                      {t}
                    </span>
                  ))}
                </div>
              )}
              {benefit.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-xs font-medium tracking-wide text-emerald-500 uppercase">Benefit</span>
                  {benefit.map(t => (
                    <span key={t} className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 text-xs font-mono font-medium">
                      {t}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Insight detail */}
          <div className="pl-8">
            <InsightCard>
              <p className="font-medium text-zinc-200 mb-1">{shock.behavior}</p>
              <p>{shock.notes}</p>
            </InsightCard>
          </div>
        </div>
      </div>
    </InsightToggle>
  )
}
