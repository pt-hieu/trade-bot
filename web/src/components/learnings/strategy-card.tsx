import { formatWinRate, accuracyColor, toTitleCase } from '../../lib/utils'
import type { StrategyInsight } from '../../types/index'

const LOW_N_THRESHOLD = 10

export function strategySubtitle(data: StrategyInsight[]): string {
  if (!data.length) return ''
  const best = data.reduce((bestSoFar, strategy) =>
    (Number(strategy.win_rate ?? 0) > Number(bestSoFar.win_rate ?? 0)) ? strategy : bestSoFar
  )
  return `best ${formatWinRate(best.win_rate)} (${toTitleCase(best.strategy)})`
}

export function StrategyContent({ data }: { data: StrategyInsight[] }) {
  if (!data.length) {
    return (
      <p className="text-xs text-muted-foreground/50 py-4">
        No strategy data yet — populates after next retrospective run.
      </p>
    )
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {data.map((strategy) => {
        const winRateNumber = Number(strategy.win_rate ?? 0)
        const barWidth = Math.max(winRateNumber * 100, 4)
        const sampleSize = Number(strategy.sample_size ?? 0)
        const isLowConfidence = sampleSize < LOW_N_THRESHOLD

        return (
          <div key={strategy.strategy} className={`space-y-1.5 ${isLowConfidence ? 'opacity-45' : ''}`}>
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] font-medium tracking-wider text-muted-foreground uppercase block">
                {toTitleCase(strategy.strategy)}
              </span>
              {isLowConfidence && (
                <span className="text-[9px] font-medium text-amber-400/80 bg-amber-500/10 border border-amber-500/20 rounded px-1 py-px">
                  Low n
                </span>
              )}
            </div>
            <p className={`text-base font-semibold font-mono tabular-nums ${accuracyColor(strategy.win_rate)}`}>
              {formatWinRate(strategy.win_rate)}
            </p>
            <div className="h-1 rounded-full bg-muted/30 overflow-hidden">
              <div
                className={`h-full rounded-full ${winRateNumber >= 0.6 ? 'bg-emerald-500/60' : winRateNumber >= 0.4 ? 'bg-amber-500/60' : 'bg-rose-500/60'}`}
                style={{ width: `${barWidth}%` }}
              />
            </div>
            <span className={`text-[10px] font-mono ${isLowConfidence ? 'text-amber-400/60' : 'text-muted-foreground/50'}`}>
              n={sampleSize}
            </span>
          </div>
        )
      })}
    </div>
  )
}
