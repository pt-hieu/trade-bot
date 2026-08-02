import { Card } from '../ui/card'
import { Badge } from '../ui/badge'
import { toTitleCase, formatWinRate } from '../../lib/utils'
import type { LearningPattern } from '../../types/index'

const ERROR_STYLES: Record<string, string> = {
  ANALYSIS_ERROR: 'border-rose-500/30 text-rose-400',
  EXECUTION_ERROR: 'border-amber-500/30 text-amber-400',
  CALIBRATION_ERROR: 'border-orange-500/30 text-orange-400',
  VARIANCE: 'border-muted-foreground/30 text-muted-foreground',
}

interface PatternsCardProps {
  title: string
  patterns: LearningPattern[]
  type: 'winning' | 'losing'
}

export function PatternsCard({ title, patterns, type }: PatternsCardProps) {
  const accentColor = type === 'winning' ? 'text-emerald-400' : 'text-rose-400'
  const ruleKey = type === 'winning' ? 'actionable_rule' : 'avoid_rule'
  const rateKey = type === 'winning' ? 'win_rate' : 'loss_rate'

  return (
    <Card className="border-border/50 p-4 space-y-1">
      <h3 className={`text-xs font-medium tracking-widest uppercase ${accentColor}`}>
        {title}
      </h3>
      {!patterns.length ? (
        <p className="text-xs text-muted-foreground/50 py-4">
          No patterns yet — need more trades with{' '}
          {type === 'winning' ? 'consistent wins' : 'repeated losses'} to detect a pattern.
        </p>
      ) : (
        <div className="space-y-0">
          {patterns.map((pattern, index) => (
            <div
              key={index}
              className="py-2 border-b border-border/15 last:border-0 space-y-0.5"
            >
              <div className="flex items-start justify-between gap-3">
                <p className="text-xs leading-snug text-foreground/90 flex-1">
                  {pattern.description}
                </p>
                <div className="flex items-center gap-1.5 shrink-0">
                  {pattern[rateKey] != null && (
                    <span
                      className={`text-[10px] font-mono font-semibold tabular-nums ${accentColor}`}
                    >
                      {formatWinRate(pattern[rateKey])}
                    </span>
                  )}
                  {pattern.sample_size != null && (
                    <span className="text-[10px] font-mono text-muted-foreground/50 tabular-nums">
                      n={pattern.sample_size}
                    </span>
                  )}
                  {type === 'losing' && pattern.dominant_error && (
                    <Badge
                      variant="outline"
                      className={`text-[10px] ${ERROR_STYLES[pattern.dominant_error] ?? 'border-muted-foreground/30 text-muted-foreground'}`}
                    >
                      {toTitleCase(pattern.dominant_error)}
                    </Badge>
                  )}
                </div>
              </div>
              {pattern[ruleKey] && (
                <p className={`text-[10px] ${accentColor}/70 leading-snug`}>
                  {pattern[ruleKey]}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
