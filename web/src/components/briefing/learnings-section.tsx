import { Card } from '../ui/card'
import { Badge } from '../ui/badge'
import { CardLabel } from '../ui/card-label'
import { toTitleCase } from '../../lib/utils'
import type { LearningsData } from '../../types/index'

interface LearningSectionProps {
  data: LearningsData
}

export function LearningsSection({ data }: LearningSectionProps) {
  const { summary, winning_patterns, losing_patterns, sector_insights, ticker_insights } = data

  return (
    <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-500" style={{ animationDelay: '420ms' }}>
      <h2 className="text-lg font-semibold tracking-tight">Learnings</h2>

      {/* Summary stats */}
      {summary && (
        <div className="flex gap-3 flex-wrap">
          <Card className="border-border/50 py-2 px-3 flex-1 min-w-[100px]">
            <CardLabel label="Days" tip="Rolling window of trading days analyzed" />
            <p className="text-lg font-semibold font-mono tabular-nums">{summary.total_days}</p>
          </Card>
          <Card className="border-border/50 py-2 px-3 flex-1 min-w-[100px]">
            <CardLabel label="Entry Hit" tip="% of BUY/ADD recs where price hit entry. Excludes AVOID/HOLD/SKIP." />
            <p className="text-lg font-semibold font-mono tabular-nums">
              {summary.overall_entry_hit_rate != null ? `${Number(summary.overall_entry_hit_rate).toFixed(0)}%` : '—'}
            </p>
          </Card>
          <Card gradient={Number(summary.overall_win_rate ?? 0) >= 50 ? 'positive' : 'negative'} className="border-border/50 py-2 px-3 flex-1 min-w-[100px]">
            <CardLabel label="Win Rate" tip="% of all recs that were correct. AVOID that avoided losses count as wins." />
            <p className={`text-lg font-semibold font-mono tabular-nums ${Number(summary.overall_win_rate ?? 0) >= 50 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {summary.overall_win_rate != null ? `${Number(summary.overall_win_rate).toFixed(0)}%` : '—'}
            </p>
          </Card>
          <Card gradient={Number(summary.avg_pnl_percent ?? 0) >= 0 ? 'positive' : 'negative'} className="border-border/50 py-2 px-3 flex-1 min-w-[100px]">
            <CardLabel label="Avg P/L" tip="Average profit/loss on trades where entry was hit" />
            <p className={`text-lg font-semibold font-mono tabular-nums ${Number(summary.avg_pnl_percent ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {summary.avg_pnl_percent != null
                ? `${Number(summary.avg_pnl_percent) >= 0 ? '+' : ''}${Number(summary.avg_pnl_percent).toFixed(1)}%`
                : '—'}
            </p>
          </Card>
        </div>
      )}

      {/* Sector insights */}
      {sector_insights.length > 0 && (
        <div>
          <div className="mb-2">
            <CardLabel label="Sector Bias" tip="Win rate of recs per sector. Green = hot, red = cold." />
          </div>
          <div className="flex gap-2 flex-wrap">
            {sector_insights.map((s) => {
              const biasColor = s.bias === 'hot' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20'
                : s.bias === 'cold' ? 'bg-rose-500/15 text-rose-400 border-rose-500/20'
                : 'bg-muted text-muted-foreground border-border'
              return (
                <Badge key={s.sector_name} className={`${biasColor} text-xs font-mono`}>
                  {toTitleCase(s.sector_name)}
                  {s.win_rate != null && (
                    <span className="ml-1 opacity-70">{(Number(s.win_rate) * 100).toFixed(0)}%</span>
                  )}
                </Badge>
              )
            })}
          </div>
        </div>
      )}

      {/* Ticker accuracy */}
      {ticker_insights.length > 0 && (
        <div>
          <div className="mb-2">
            <CardLabel label="Ticker Accuracy" tip="Recent recommendation accuracy per ticker. Green >= 60%, amber >= 40%, red < 40%." />
          </div>
          <div className="flex gap-2 flex-wrap">
            {ticker_insights.map((t) => {
              const acc = Number(t.recent_accuracy ?? 0) * 100
              const color = acc >= 60 ? 'text-emerald-400' : acc >= 40 ? 'text-amber-400' : 'text-rose-400'
              return (
                <span key={t.ticker} className="text-xs font-mono">
                  <span className="text-foreground">{t.ticker}</span>
                  <span className={`ml-1 ${color}`}>{acc.toFixed(0)}%</span>
                </span>
              )
            })}
          </div>
        </div>
      )}

      {/* Patterns */}
      {(winning_patterns.length > 0 || losing_patterns.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Winning */}
          {winning_patterns.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-medium tracking-widest text-emerald-400 uppercase">
                Winning Patterns
              </h3>
              {winning_patterns.map((p, i) => (
                <Card key={i} gradient="positive" className="border-emerald-500/20 py-2 px-3">
                  <p className="text-sm leading-relaxed">{p.description}</p>
                  {p.actionable_rule && (
                    <p className="text-xs text-emerald-400 mt-1">{p.actionable_rule}</p>
                  )}
                  {p.win_rate != null && (
                    <span className="text-xs font-mono text-muted-foreground mt-1 block">
                      Win: {(Number(p.win_rate) * 100).toFixed(0)}%
                      {p.sample_size != null && ` (n=${p.sample_size})`}
                    </span>
                  )}
                </Card>
              ))}
            </div>
          )}

          {/* Losing */}
          {losing_patterns.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-medium tracking-widest text-rose-400 uppercase">
                Losing Patterns
              </h3>
              {losing_patterns.map((p, i) => (
                <Card key={i} gradient="negative" className="border-rose-500/20 py-2 px-3">
                  <p className="text-sm leading-relaxed">{p.description}</p>
                  {p.avoid_rule && (
                    <p className="text-xs text-rose-400 mt-1">{p.avoid_rule}</p>
                  )}
                  {p.loss_rate != null && (
                    <span className="text-xs font-mono text-muted-foreground mt-1 block">
                      Loss: {(Number(p.loss_rate) * 100).toFixed(0)}%
                      {p.sample_size != null && ` (n=${p.sample_size})`}
                    </span>
                  )}
                </Card>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
