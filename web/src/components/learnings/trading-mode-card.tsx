import { Badge } from '../ui/badge'
import { CardLabel } from '../ui/card-label'
import { formatWinRate, accuracyColor } from '../../lib/utils'
import type { TradingModePatterns } from '../../types/index'

export function tradingModeSubtitle(data: TradingModePatterns | null): string {
  if (!data) return ''
  const compliance = Number(data.mode_compliance_rate ?? 0)
  return `${(compliance * 100).toFixed(0)}% compliance`
}

export function TradingModeContent({ data }: { data: TradingModePatterns }) {
  const compliance = Number(data.mode_compliance_rate ?? 0)
  const winRate = Number(data.mode_appropriate_win_rate ?? 0)

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-0.5">
          <CardLabel label="Compliance" tip="% of midday sessions where recommendations followed the prescribed trading mode (NORMAL/LOW_CASH/REALLOCATION)" />
          <p
            className={`text-base font-semibold font-mono tabular-nums ${accuracyColor(compliance, { high: 0.80, mid: 0.60 })}`}
          >
            {formatWinRate(data.mode_compliance_rate)}
          </p>
        </div>
        <div className="space-y-0.5">
          <CardLabel label="On-mode win rate" tip="Win rate of trades taken on mode-compliant days. Higher = following the mode leads to better outcomes." />
          <p className={`text-base font-semibold font-mono tabular-nums ${winRate >= 0.50 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {formatWinRate(data.mode_appropriate_win_rate)}
          </p>
        </div>
      </div>

      {data.mode_violations.length > 0 && (
        <div>
          <p className="text-[10px] font-medium tracking-wider text-rose-400 uppercase mb-2">Violations</p>
          <div className="flex flex-wrap gap-1.5">
            {data.mode_violations.map((violation, index) => (
              <Badge key={index} className="bg-rose-500/10 text-rose-400 border-rose-500/20 text-xs">
                {violation}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
