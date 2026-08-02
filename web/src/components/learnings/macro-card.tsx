import { CardLabel } from '../ui/card-label'
import { formatPct, formatWinRate, accuracyColor } from '../../lib/utils'
import type { MacroPatterns } from '../../types/index'

const REGIME_COLORS: Record<string, string> = {
  CALM: 'text-emerald-400',
  CAUTIOUS: 'text-amber-400',
  ELEVATED: 'text-orange-400',
  CRISIS: 'text-rose-400',
}

export function macroSubtitle(data: MacroPatterns | null): string {
  if (!data) return ''
  return `${formatWinRate(data.overall_accuracy)} accuracy · ${data.total_days ?? 0} days`
}

export function MacroContent({ data }: { data: MacroPatterns }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-4 gap-4">
        <div className="space-y-0.5">
          <CardLabel label="Overall" tip="% of days where the predicted macro regime (CALM/CAUTIOUS/ELEVATED/CRISIS) matched actual market conditions." />
          <p className={`text-base font-semibold font-mono tabular-nums ${accuracyColor(data.overall_accuracy)}`}>
            {formatWinRate(data.overall_accuracy)}
          </p>
        </div>
        <div className="space-y-0.5">
          <CardLabel label="False alarms" tip="ELEVATED/CRISIS predictions where VN-Index rallied >1%. Over-cautious calls that blocked entries unnecessarily." />
          <p className="text-base font-semibold font-mono tabular-nums">
            {data.false_alarms ?? '—'}
          </p>
        </div>
        <div className="space-y-0.5">
          <CardLabel label="Missed drops" tip="CALM predictions where VN-Index dropped >1%. Under-cautious calls that missed downside risk." />
          <p className="text-base font-semibold font-mono tabular-nums">
            {data.missed_drops ?? '—'}
          </p>
        </div>
        <div className="space-y-0.5">
          <CardLabel label="Missed opps" tip="Defensive regime (CAUTIOUS/ELEVATED/CRISIS) days where VN-Index rallied >1.5%. Opportunity cost of over-caution." />
          <p className="text-base font-semibold font-mono tabular-nums">
            {data.missed_opportunities ?? '—'}
          </p>
        </div>
      </div>

      {data.regime_accuracy.length > 0 && (
        <div className="space-y-1">
          <div className="grid grid-cols-4 gap-2 text-[10px] font-medium text-muted-foreground uppercase tracking-wider pb-1 border-b border-border/30">
            <span>Regime</span>
            <span>Days</span>
            <span>Correct</span>
            <span>Avg VNI chg</span>
          </div>
          {data.regime_accuracy.map((regime) => {
            const accuracy = regime.days_count && regime.correct_count
              ? regime.correct_count / regime.days_count
              : null
            return (
              <div key={regime.regime} className="grid grid-cols-4 gap-2 text-xs">
                <span className={`font-medium ${REGIME_COLORS[regime.regime] ?? 'text-muted-foreground'}`}>
                  {regime.regime}
                </span>
                <span className="font-mono tabular-nums text-muted-foreground">{regime.days_count ?? '—'}</span>
                <span className={`font-mono tabular-nums ${accuracy != null ? accuracyColor(accuracy) : 'text-muted-foreground'}`}>
                  {accuracy != null ? formatWinRate(accuracy) : '—'}
                </span>
                <span className={`font-mono tabular-nums ${Number(regime.avg_vn_change ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {formatPct(regime.avg_vn_change)}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
