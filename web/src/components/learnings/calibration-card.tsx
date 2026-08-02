import { CardLabel } from '../ui/card-label'
import { AlertTriangle } from 'lucide-react'
import type { CalibrationInsights } from '../../types/index'

const LOW_CONFIDENCE_THRESHOLD = 5

function pct(value: number | null, decimals = 1) {
  return value != null ? `${Number(value).toFixed(decimals)}%` : '—'
}

function ratio(value: number | null) {
  return value != null ? `${Number(value).toFixed(2)}x` : '—'
}

function rawCount(percentage: number | null, total: number | null): number | null {
  if (percentage == null || total == null) return null
  return Math.round((Number(percentage) / 100) * Number(total))
}

function Stat({
  label,
  tip,
  color,
  children,
  dimmed,
}: {
  label: string
  tip: string
  color?: string
  children: React.ReactNode
  dimmed?: boolean
}) {
  return (
    <div className={`space-y-1 ${dimmed ? 'opacity-40' : ''}`}>
      <CardLabel label={label} tip={tip} />
      <div className={`text-base font-semibold font-mono tabular-nums ${color ?? 'text-foreground'}`}>
        {children}
      </div>
    </div>
  )
}

function RawCountAnnotation({ numerator, denominator }: { numerator: number; denominator: number }) {
  return (
    <span className="text-[10px] text-muted-foreground/60 font-mono block mt-0.5">
      {numerator} / {denominator}
    </span>
  )
}

/** Summary line for collapsed diagnostic header */
export function calibrationSubtitle(data: CalibrationInsights | null): string {
  if (!data) return ''
  const unreachable = Number(data.pct_entries_unreachable ?? 0)
  const sampleSize = Number(data.sample_size ?? 0)
  return `${unreachable.toFixed(0)}% unreachable · n=${sampleSize}`
}

export function CalibrationContent({ data }: { data: CalibrationInsights }) {
  const sampleSize = Number(data.sample_size ?? 0)
  const lowConfidence = sampleSize < LOW_CONFIDENCE_THRESHOLD
  const showRawCounts = sampleSize <= 15

  const unreachable = Number(data.pct_entries_unreachable ?? 0)
  const tooTight = Number(data.pct_stops_too_tight ?? 0)
  const stopAtr = Number(data.avg_stop_vs_atr ?? 0)
  const entryGap = Number(data.avg_entry_gap_pct ?? 0)
  const targetHitRate = Number(data.target_hit_rate ?? 0)

  const unreachableCount = rawCount(data.pct_entries_unreachable, data.sample_size)
  const enteredCount = unreachableCount != null ? sampleSize - unreachableCount : null
  const targetsHitCount = enteredCount != null ? rawCount(data.target_hit_rate, enteredCount) : null

  return (
    <div className="space-y-1">
      {lowConfidence && (
        <span className="inline-flex items-center gap-1 text-[10px] font-medium text-amber-400/80 bg-amber-500/10 border border-amber-500/20 rounded-md px-1.5 py-0.5 mb-2">
          <AlertTriangle className="h-2.5 w-2.5" />
          Low sample (n={sampleSize})
        </span>
      )}

      <div className="grid grid-cols-3 gap-4">
        <Stat
          label="Entry gap"
          tip="Avg % gap between recommended entry and day low. Negative = entry was below the low (unreachable)."
          color={entryGap < -3 ? 'text-rose-400' : entryGap < 0 ? 'text-amber-400' : 'text-emerald-400'}
          dimmed={lowConfidence}
        >
          {pct(data.avg_entry_gap_pct)}
        </Stat>

        <Stat
          label="Unreachable"
          tip="% of entries where price never reached the recommended entry level"
          color={unreachable > 40 ? 'text-rose-400' : unreachable > 20 ? 'text-amber-400' : 'text-emerald-400'}
          dimmed={lowConfidence}
        >
          {pct(data.pct_entries_unreachable, 0)}
          {showRawCounts && unreachableCount != null && (
            <RawCountAnnotation numerator={unreachableCount} denominator={sampleSize} />
          )}
        </Stat>

        <Stat
          label="Target hit"
          tip="% of filled positions that reached target price. Denominator = entries that filled, not total recommendations."
          color={
            enteredCount != null && enteredCount < 3
              ? 'text-muted-foreground'
              : targetHitRate >= 50
                ? 'text-emerald-400'
                : targetHitRate >= 30
                  ? 'text-amber-400'
                  : 'text-rose-400'
          }
          dimmed={lowConfidence}
        >
          {enteredCount != null && enteredCount < 3 ? (
            <>
              <span className="text-muted-foreground">
                {targetsHitCount ?? 0}/{enteredCount}
              </span>
              <span className="text-[10px] text-muted-foreground/60 block mt-0.5">too few fills</span>
            </>
          ) : (
            <>
              {pct(data.target_hit_rate, 0)}
              {showRawCounts && targetsHitCount != null && enteredCount != null && (
                <RawCountAnnotation numerator={targetsHitCount} denominator={enteredCount} />
              )}
            </>
          )}
        </Stat>

        <Stat
          label="Stop / ATR"
          tip="Avg stop distance as multiple of ATR. Below 1.0x = stops tighter than normal volatility, likely noise stop-outs."
          color={stopAtr < 1.0 ? 'text-rose-400' : stopAtr < 1.5 ? 'text-amber-400' : 'text-emerald-400'}
          dimmed={lowConfidence}
        >
          {ratio(data.avg_stop_vs_atr)}
        </Stat>

        <Stat
          label="Stops tight"
          tip="% of entries with stop/ATR below 1.0x — vulnerable to noise stop-outs"
          color={tooTight > 30 ? 'text-rose-400' : tooTight > 15 ? 'text-amber-400' : 'text-emerald-400'}
          dimmed={lowConfidence}
        >
          {pct(data.pct_stops_too_tight, 0)}
        </Stat>

        <Stat
          label="R:R"
          tip="Predicted vs actual reward-to-risk available in market. Large gap = overconfident targets or tight stops."
          dimmed={lowConfidence}
        >
          <span className="text-muted-foreground text-xs mr-1">pred</span>
          {ratio(data.avg_predicted_rr)}
          <span className="text-muted-foreground mx-1">→</span>
          <span className="text-muted-foreground text-xs mr-1">actual</span>
          {ratio(data.avg_actual_rr)}
        </Stat>
      </div>
    </div>
  )
}
