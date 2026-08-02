import { Link } from '@tanstack/react-router'
import { ArrowRight } from 'lucide-react'
import { Badge } from './ui/badge'
import { cn, toTitleCase } from '../lib/utils'
import { useDailyIntel } from '../hooks/use-intel'
import type { MarketRegime, GlobalRiskRegime } from '../types/index'

const REGIME_DOT: Record<MarketRegime, string> = {
  RISK_ON: 'bg-emerald-500',
  NEUTRAL: 'bg-amber-500',
  RISK_OFF: 'bg-rose-500',
}

const REGIME_LABEL: Record<MarketRegime, string> = {
  RISK_ON: 'Risk On',
  NEUTRAL: 'Neutral',
  RISK_OFF: 'Risk Off',
}

const RISK_COLORS: Record<GlobalRiskRegime, string> = {
  CALM: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
  CAUTIOUS: 'bg-amber-500/15 text-amber-400 border-amber-500/20',
  ELEVATED: 'bg-orange-500/15 text-orange-400 border-orange-500/20',
  CRISIS: 'bg-rose-500/15 text-rose-400 border-rose-500/20',
}

const REGIME_GRADIENT: Record<MarketRegime, string> = {
  RISK_ON: 'gradient-positive',
  NEUTRAL: 'gradient-warning',
  RISK_OFF: 'gradient-negative',
}

export function IntelSummary() {
  const { data: intel, isLoading, error } = useDailyIntel()

  if (isLoading) return null

  if (error || !intel?.regime) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-border/50 px-4 py-3 text-muted-foreground text-sm">
        Market data unavailable
      </div>
    )
  }

  const { regime: regimeRaw, macro, rotation } = intel
  const regime = regimeRaw as { regime: MarketRegime; vn_index_value?: number; vn_index_change_pct?: number }
  const changePct = Number(regime.vn_index_change_pct ?? 0)
  const changeColor = changePct > 0 ? 'text-emerald-400' : changePct < 0 ? 'text-rose-400' : 'text-muted-foreground'

  const riskRegime = (macro as any)?.global_risk_regime as GlobalRiskRegime | undefined

  return (
    <Link
      to="/briefing" search={{} as any}
      className={cn(
        "flex items-center gap-4 rounded-xl border border-border/50 px-4 py-3 hover:border-border transition-colors cursor-pointer group flex-wrap",
        REGIME_GRADIENT[regime.regime]
      )}
      data-test-id="intel-summary"
    >
      {/* Regime */}
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${REGIME_DOT[regime.regime]} animate-pulse`} />
        <span className="text-sm font-medium">{REGIME_LABEL[regime.regime]}</span>
      </div>

      {/* VN-Index */}
      <div className="flex items-baseline gap-1.5">
        <span className="text-xs text-muted-foreground">VN-Index</span>
        <span className="font-mono text-sm font-semibold tabular-nums">
          {regime.vn_index_value != null ? Number(regime.vn_index_value).toFixed(1) : '—'}
        </span>
        <span className={`font-mono text-xs tabular-nums ${changeColor}`}>
          {changePct !== 0 ? `${changePct > 0 ? '+' : ''}${changePct.toFixed(2)}%` : ''}
        </span>
      </div>

      {/* Global risk */}
      {macro && riskRegime && riskRegime in RISK_COLORS && (
        <Badge className={`text-[10px] ${RISK_COLORS[riskRegime]}`}>
          {toTitleCase(riskRegime)}
        </Badge>
      )}

      {/* Hot sectors */}
      {rotation?.hot_sectors.slice(0, 3).map((s) => (
        <Badge key={s.sector_name} variant="secondary" className="text-[10px] font-mono hidden sm:inline-flex">
          {toTitleCase(s.sector_name)}
        </Badge>
      ))}

      {/* Arrow */}
      <ArrowRight className="w-3.5 h-3.5 text-muted-foreground ml-auto group-hover:translate-x-0.5 transition-transform" />
    </Link>
  )
}
