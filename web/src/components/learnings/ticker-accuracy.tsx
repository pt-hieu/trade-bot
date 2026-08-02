import { accuracyColor } from '../../lib/utils'
import type { TickerInsight } from '../../types/index'

export function tickerAccuracySubtitle(insights: TickerInsight[]): string {
  if (!insights.length) return ''
  const failing = insights.filter((ticker) => Number(ticker.recent_accuracy ?? 0) < 0.4)
  if (failing.length > 0) return `${failing.length} ticker${failing.length !== 1 ? 's' : ''} below 40%`
  const best = Math.max(...insights.map((ticker) => Number(ticker.recent_accuracy ?? 0)))
  return `best ${(best * 100).toFixed(0)}% · ${insights.length} tickers`
}

export function TickerAccuracyContent({ insights }: { insights: TickerInsight[] }) {
  if (!insights.length) return null

  return (
    <div className="space-y-1">
      <div className="grid grid-cols-[1fr_auto_auto] gap-x-3 gap-y-0.5 text-[10px] font-medium text-muted-foreground uppercase tracking-wider pb-1 border-b border-border/30">
        <span>Ticker</span>
        <span>Accuracy</span>
        <span />
      </div>
      {insights.map((ticker) => {
        const accuracy = Number(ticker.recent_accuracy ?? 0)
        const accuracyPct = (accuracy * 100).toFixed(0)
        const color = accuracyColor(accuracy)
        const barWidth = Math.max(accuracy * 100, 2)

        return (
          <div
            key={ticker.ticker}
            className="grid grid-cols-[1fr_auto_60px] gap-x-3 items-center py-1 border-b border-border/10 last:border-0"
          >
            <span className="text-xs font-medium">{ticker.ticker}</span>
            <span className={`text-xs font-mono tabular-nums font-semibold ${color}`}>
              {accuracyPct}%
            </span>
            <div className="h-1 rounded-full bg-muted/30 overflow-hidden">
              <div
                className={`h-full rounded-full ${
                  accuracy >= 0.6
                    ? 'bg-emerald-400'
                    : accuracy >= 0.4
                      ? 'bg-amber-400'
                      : 'bg-rose-400'
                }`}
                style={{ width: `${barWidth}%` }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}
