import { InsightToggle, InsightTrigger, InsightCard } from '../ui/detail-text'
import type { RegimeData, MarketRegime } from '../../types/index'

const REGIME_CONFIG: Record<MarketRegime, { label: string; bg: string; dot: string; text: string }> = {
  RISK_ON: {
    label: 'Risk On',
    bg: 'from-emerald-500/8 via-emerald-500/4 to-transparent',
    dot: 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]',
    text: 'text-emerald-400',
  },
  NEUTRAL: {
    label: 'Neutral',
    bg: 'from-amber-500/8 via-amber-500/4 to-transparent',
    dot: 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.6)]',
    text: 'text-amber-400',
  },
  RISK_OFF: {
    label: 'Risk Off',
    bg: 'from-rose-500/8 via-rose-500/4 to-transparent',
    dot: 'bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.6)]',
    text: 'text-rose-400',
  },
}

interface RegimeStripProps {
  regime: RegimeData
}

export function RegimeStrip({ regime }: RegimeStripProps) {
  const config = REGIME_CONFIG[regime.regime]
  const changePct = Number(regime.vn_index_change_pct ?? 0)
  const changeColor = changePct > 0 ? 'text-emerald-400' : changePct < 0 ? 'text-rose-400' : 'text-muted-foreground'
  const changeSign = changePct > 0 ? '+' : ''

  return (
    <InsightToggle>
      <div className="space-y-3">
        <div
          className={`relative rounded-xl border border-border/50 bg-gradient-to-r ${config.bg} px-5 py-4 animate-in fade-in duration-500`}
        >
          <div className="flex items-center justify-between flex-wrap gap-3">
            {/* Regime badge */}
            <div className="flex items-center gap-3">
              <div className={`w-2.5 h-2.5 rounded-full ${config.dot} animate-pulse`} />
              <span className={`text-sm font-semibold tracking-wide ${config.text}`}>
                {config.label}
              </span>
              {regime.regime_confidence != null && (
                <span className="text-xs text-muted-foreground font-mono tabular-nums">
                  {(Number(regime.regime_confidence) * 100).toFixed(0)}%
                </span>
              )}
            </div>

            {/* VN-Index */}
            <div className="flex items-baseline gap-2">
              <span className="text-xs text-muted-foreground uppercase tracking-widest">VN-Index</span>
              <span className="text-lg font-semibold font-mono tabular-nums tracking-tight">
                {regime.vn_index_value != null ? Number(regime.vn_index_value).toFixed(1) : '—'}
              </span>
              <span className={`text-sm font-mono tabular-nums ${changeColor}`}>
                {changePct !== 0 ? `${changeSign}${changePct.toFixed(2)}%` : '—'}
              </span>
            </div>

            {/* Insight toggle on right */}
            {regime.key_signal && <InsightTrigger />}
          </div>
        </div>

        {/* Insight card below strip */}
        {regime.key_signal && (
          <InsightCard>{regime.key_signal}</InsightCard>
        )}
      </div>
    </InsightToggle>
  )
}
