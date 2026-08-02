import { useState } from 'react'
import { Card } from '../ui/card'
import { CardLabel } from '../ui/card-label'
import { Clock, ChevronDown, ChevronUp } from 'lucide-react'
import { formatWinRate } from '../../lib/utils'
import type { MiddayPatterns } from '../../types/index'

const TRUNCATE_LENGTH = 100

function TruncatedItem({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false)
  const needsTruncation = text.length > TRUNCATE_LENGTH

  if (!needsTruncation) {
    return <span className="text-xs text-muted-foreground leading-snug">{text}</span>
  }

  return (
    <span className="text-xs text-muted-foreground leading-snug">
      {expanded ? text : `${text.slice(0, TRUNCATE_LENGTH)}...`}
      <button
        onClick={() => setExpanded(!expanded)}
        className="ml-1 text-[10px] text-muted-foreground/60 hover:text-muted-foreground cursor-pointer inline-flex items-center"
      >
        {expanded ? (
          <>less <ChevronUp className="h-2.5 w-2.5 ml-0.5" /></>
        ) : (
          <>more <ChevronDown className="h-2.5 w-2.5 ml-0.5" /></>
        )}
      </button>
    </span>
  )
}

export function MiddayCard({ data }: { data: MiddayPatterns | null }) {
  if (!data) return null

  const winRate = Number(data.adjustment_win_rate ?? 0)
  const improvement = Number(data.average_improvement ?? 0)

  return (
    <Card className="border-border/50 p-4 space-y-1">
      <div className="flex items-center gap-2">
        <Clock className="h-4 w-4 text-muted-foreground/60" />
        <h3 className="text-sm font-medium">Midday check</h3>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="space-y-0.5">
          <CardLabel label="Sessions" tip="Number of trading days with a midday check in the rolling window" />
          <p className="text-base font-semibold font-mono tabular-nums">{data.days_with_midday ?? '—'}</p>
        </div>
        <div className="space-y-0.5">
          <CardLabel label="Adj win rate" tip="% of midday adjustments that were helpful. Helpful = adjustment improved the outcome vs morning recommendation." />
          <p className={`text-base font-semibold font-mono tabular-nums ${winRate >= 0.50 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {formatWinRate(data.adjustment_win_rate)}
          </p>
        </div>
        <div className="space-y-0.5">
          <CardLabel label="Avg improvement" tip="Average afternoon accuracy across sessions. Higher = midday adjustments consistently improve outcomes." />
          <p className={`text-base font-semibold font-mono tabular-nums ${improvement >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {data.average_improvement != null ? `${improvement >= 0 ? '+' : ''}${Number(data.average_improvement).toFixed(1)}%` : '—'}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {data.when_helpful.length > 0 && (
          <div>
            <p className="text-[10px] font-medium tracking-wider text-emerald-400 uppercase mb-1.5">Helps when</p>
            <ul className="space-y-1.5">
              {data.when_helpful.map((item, index) => (
                <li key={index} className="flex gap-1.5">
                  <span className="text-emerald-400/60 text-xs shrink-0">·</span>
                  <TruncatedItem text={item} />
                </li>
              ))}
            </ul>
          </div>
        )}
        {data.when_harmful.length > 0 && (
          <div>
            <p className="text-[10px] font-medium tracking-wider text-rose-400 uppercase mb-1.5">Hurts when</p>
            <ul className="space-y-1.5">
              {data.when_harmful.map((item, index) => (
                <li key={index} className="flex gap-1.5">
                  <span className="text-rose-400/60 text-xs shrink-0">·</span>
                  <TruncatedItem text={item} />
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  )
}
