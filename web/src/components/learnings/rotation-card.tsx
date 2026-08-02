import { Badge } from '../ui/badge'
import { CardLabel } from '../ui/card-label'
import { toTitleCase, formatWinRate, formatPct, accuracyColor } from '../../lib/utils'
import type { RotationPatterns, SectorInsight } from '../../types/index'

export function rotationSubtitle(data: RotationPatterns | null): string {
  if (!data) return ''
  return `${formatWinRate(data.overall_accuracy)} accuracy · ${data.total_days ?? 0} days`
}

export function RotationContent({
  data,
  sectorInsights,
}: {
  data: RotationPatterns
  sectorInsights?: SectorInsight[]
}) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-4">
        <div className="space-y-0.5">
          <CardLabel label="Overall" tip="Average of hot and cold hit rates. Measures how well sector rotation predictions match actual sector performance." />
          <p className={`text-base font-semibold font-mono tabular-nums ${accuracyColor(data.overall_accuracy)}`}>
            {formatWinRate(data.overall_accuracy)}
          </p>
        </div>
        <div className="space-y-0.5">
          <CardLabel label="Hot hit rate" tip="% of sectors predicted as hot that actually outperformed the market average." />
          <p className={`text-base font-semibold font-mono tabular-nums ${accuracyColor(data.hot_hit_rate)}`}>
            {formatWinRate(data.hot_hit_rate)}
          </p>
        </div>
        <div className="space-y-0.5">
          <CardLabel label="Cold hit rate" tip="% of sectors predicted as cold that actually underperformed the market average." />
          <p className={`text-base font-semibold font-mono tabular-nums ${accuracyColor(data.cold_hit_rate)}`}>
            {formatWinRate(data.cold_hit_rate)}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-0.5">
          <CardLabel label="Hot vs market" tip="Avg return differential of hot-sector picks vs market. Positive = hot sectors outperformed." />
          <p className={`text-base font-semibold font-mono tabular-nums ${Number(data.avg_hot_vs_market ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {formatPct(data.avg_hot_vs_market != null ? Number(data.avg_hot_vs_market) * 100 : null, 1)}
          </p>
        </div>
        <div className="space-y-0.5">
          <CardLabel label="Cold vs market" tip="Avg return differential of cold-sector picks vs market. Negative = cold sectors underperformed (correct prediction)." />
          <p className={`text-base font-semibold font-mono tabular-nums ${Number(data.avg_cold_vs_market ?? 0) <= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {formatPct(data.avg_cold_vs_market != null ? Number(data.avg_cold_vs_market) * 100 : null, 1)}
          </p>
        </div>
      </div>

      {data.sector_scores.length > 0 && (
        <div className="space-y-1">
          <div className="grid grid-cols-3 gap-2 text-[10px] font-medium text-muted-foreground uppercase tracking-wider pb-1 border-b border-border/30">
            <span>Sector</span>
            <span>As hot</span>
            <span>As cold</span>
          </div>
          {data.sector_scores.map((sectorScore) => (
            <div key={sectorScore.sector_name} className="grid grid-cols-3 gap-2 text-xs">
              <span className="text-muted-foreground truncate">{toTitleCase(sectorScore.sector_name)}</span>
              <span className={`font-mono tabular-nums ${accuracyColor(sectorScore.as_hot_accuracy)}`}>
                {formatWinRate(sectorScore.as_hot_accuracy)}
              </span>
              <span className={`font-mono tabular-nums ${accuracyColor(sectorScore.as_cold_accuracy)}`}>
                {formatWinRate(sectorScore.as_cold_accuracy)}
              </span>
            </div>
          ))}
        </div>
      )}

      {sectorInsights && sectorInsights.length > 0 && (
        <div className="space-y-1.5 pt-1 border-t border-border/15">
          <CardLabel
            label="Recommendation concentration"
            tip="Win rate of recommendations per sector. Shows which sectors the pipeline favors and whether that bias pays off."
          />
          <div className="flex gap-1.5 flex-wrap">
            {sectorInsights.map((insight) => {
              const winRate = Number(insight.win_rate ?? 0) * 100
              const biasColor =
                insight.bias === 'hot'
                  ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20'
                  : insight.bias === 'cold'
                    ? 'bg-rose-500/15 text-rose-400 border-rose-500/20'
                    : 'bg-muted text-muted-foreground border-border'
              return (
                <Badge key={insight.sector_name} className={`${biasColor} text-[10px] font-mono`}>
                  {toTitleCase(insight.sector_name)}
                  {insight.win_rate != null && (
                    <span className="ml-1 opacity-70">{winRate.toFixed(0)}% win</span>
                  )}
                </Badge>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
