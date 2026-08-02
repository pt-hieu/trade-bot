import { Card } from '../ui/card'
import { InsightToggle, InsightTrigger, InsightCard } from '../ui/detail-text'
import { cn, toTitleCase } from '../../lib/utils'
import type { MacroData, GlobalRiskRegime, VixSignal, DxySignal, UsdVndSignal } from '../../types/index'

// ── Config ───────────────────────────────────────────────────────────────────

const RISK_COLORS: Record<GlobalRiskRegime, { color: string; label: string }> = {
  CALM: { color: 'text-emerald-400', label: 'Calm' },
  CAUTIOUS: { color: 'text-amber-400', label: 'Cautious' },
  ELEVATED: { color: 'text-orange-400', label: 'Elevated' },
  CRISIS: { color: 'text-rose-400', label: 'Crisis' },
}

const VIX_COLORS: Record<VixSignal, string> = {
  LOW: 'text-emerald-400',
  MODERATE: 'text-amber-400',
  HIGH: 'text-orange-400',
  EXTREME: 'text-rose-400',
}

const DXY_COLORS: Record<DxySignal, string> = {
  WEAK: 'text-emerald-400',
  NEUTRAL: 'text-muted-foreground',
  STRONG: 'text-rose-400',
}

const VND_COLORS: Record<UsdVndSignal, string> = {
  STABLE: 'text-emerald-400',
  PRESSURE: 'text-amber-400',
  FLIGHT: 'text-rose-400',
}

type Gradient = 'positive' | 'negative' | 'warning'

const RISK_GRADIENT: Record<GlobalRiskRegime, Gradient> = {
  CALM: 'positive', CAUTIOUS: 'warning', ELEVATED: 'negative', CRISIS: 'negative',
}
const DXY_GRADIENT: Record<DxySignal, Gradient | undefined> = {
  WEAK: 'positive', NEUTRAL: undefined, STRONG: 'negative',
}
const VIX_GRADIENT: Record<VixSignal, Gradient> = {
  LOW: 'positive', MODERATE: 'warning', HIGH: 'negative', EXTREME: 'negative',
}
const VND_GRADIENT: Record<UsdVndSignal, Gradient> = {
  STABLE: 'positive', PRESSURE: 'warning', FLIGHT: 'negative',
}

// ── Metric Card ──────────────────────────────────────────────────────────────

interface MacroCardProps {
  label: string
  value: string
  /** Color for the value text itself (e.g. Global Risk where value IS the signal) */
  valueColor?: string
  change?: string
  /** Invert change coloring (+ = bad, - = good) for inverse indicators like DXY/VIX */
  invertChange?: boolean
  signal?: string
  signalColor?: string
  gradient?: 'positive' | 'negative' | 'warning'
}

function changeColor(change: string, invert: boolean): string {
  const isPositive = change.startsWith('+')
  const isNegative = change.startsWith('-')
  if (!isPositive && !isNegative) return 'text-muted-foreground'
  if (invert) return isPositive ? 'text-rose-500' : 'text-emerald-500'
  return isPositive ? 'text-emerald-500' : 'text-rose-500'
}

function MacroCard({ label, value, valueColor, change, invertChange, signal, signalColor, gradient }: MacroCardProps) {
  return (
    <Card gradient={gradient} className="border-border/50 py-3 px-4 flex-1 min-w-[120px]">
      <p className="text-xs font-medium tracking-widest text-muted-foreground uppercase truncate">
        {label}
      </p>
      <div className="flex items-baseline gap-2">
        <p className={cn(
          'text-lg font-semibold tracking-tight font-mono tabular-nums',
          valueColor,
        )}>
          {value}
        </p>
        {signal && (
          <span className={cn('text-xs font-medium tracking-wide', signalColor ?? 'text-muted-foreground')}>
            {signal}
          </span>
        )}
      </div>
      {change && (
        <p className={cn(
          'text-xs font-mono tabular-nums',
          changeColor(change, invertChange ?? false),
        )}>
          {change}
        </p>
      )}
    </Card>
  )
}

// ── Main ─────────────────────────────────────────────────────────────────────

interface MacroSectionProps {
  macro: MacroData
}

export function MacroSection({ macro }: MacroSectionProps) {
  const riskRegime = macro.global_risk_regime
  const riskConfig = riskRegime && riskRegime in RISK_COLORS
    ? RISK_COLORS[riskRegime]
    : { color: 'text-muted-foreground', label: 'N/A' }
  const dxyChange = macro.dxy_change_pct != null
    ? `${Number(macro.dxy_change_pct) > 0 ? '+' : ''}${Number(macro.dxy_change_pct).toFixed(2)}%`
    : undefined
  const vixChange = macro.vix_change_pct != null
    ? `${Number(macro.vix_change_pct) > 0 ? '+' : ''}${Number(macro.vix_change_pct).toFixed(2)}%`
    : undefined

  return (
    <InsightToggle>
      <div className="space-y-3 animate-in fade-in slide-in-from-bottom-2 duration-500" style={{ animationDelay: '60ms' }}>
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold tracking-tight">Global Macro</h2>
          {macro.interpretation && <InsightTrigger />}
        </div>
        <div className="flex gap-3 flex-wrap">
          <MacroCard
            label="Global Risk"
            value={riskConfig.label}
            valueColor={riskConfig.color}
            gradient={riskRegime && riskRegime in RISK_GRADIENT ? RISK_GRADIENT[riskRegime] : undefined}
          />
          <MacroCard
            label="DXY"
            value={macro.dxy_value != null ? Number(macro.dxy_value).toFixed(2) : '—'}
            change={dxyChange}
            invertChange
            signal={macro.dxy_signal ? toTitleCase(macro.dxy_signal) : undefined}
            signalColor={macro.dxy_signal ? DXY_COLORS[macro.dxy_signal] : undefined}
            gradient={macro.dxy_signal ? DXY_GRADIENT[macro.dxy_signal] : undefined}
          />
          <MacroCard
            label="VIX"
            value={macro.vix_value != null ? Number(macro.vix_value).toFixed(1) : '—'}
            change={vixChange}
            invertChange
            signal={macro.vix_signal ? toTitleCase(macro.vix_signal) : undefined}
            signalColor={macro.vix_signal ? VIX_COLORS[macro.vix_signal] : undefined}
            gradient={macro.vix_signal ? VIX_GRADIENT[macro.vix_signal] : undefined}
          />
          <MacroCard
            label="USD/VND"
            value={macro.usd_vnd_rate != null ? Number(macro.usd_vnd_rate).toLocaleString() : '—'}
            signal={macro.usd_vnd_signal ? toTitleCase(macro.usd_vnd_signal) : undefined}
            signalColor={macro.usd_vnd_signal ? VND_COLORS[macro.usd_vnd_signal] : undefined}
            gradient={macro.usd_vnd_signal ? VND_GRADIENT[macro.usd_vnd_signal] : undefined}
          />
        </div>
        {macro.interpretation && (
          <InsightCard>{macro.interpretation}</InsightCard>
        )}
      </div>
    </InsightToggle>
  )
}
