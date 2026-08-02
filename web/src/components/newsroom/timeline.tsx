import { useMemo } from 'react'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { cn } from '../../lib/utils'
import { formatMinDate } from '../../lib/date'
import type { Narrative, Catalyst, SentimentShift } from '../../types/index'

const SHIFT_DOT: Record<SentimentShift, string> = {
  strengthens: 'bg-emerald-500',
  weakens: 'bg-rose-500',
  neutral: 'bg-muted-foreground/40',
}

const SHIFT_LABEL: Record<SentimentShift, string> = {
  strengthens: 'Strengthens',
  weakens: 'Weakens',
  neutral: 'Neutral',
}

function ShiftIcon({ shift }: { shift: SentimentShift | null }) {
  if (shift === 'strengthens') return <TrendingUp className="w-3.5 h-3.5 text-emerald-500" />
  if (shift === 'weakens') return <TrendingDown className="w-3.5 h-3.5 text-rose-500" />
  return <Minus className="w-3.5 h-3.5 text-muted-foreground/40" />
}

type TimelineEntry =
  | { kind: 'update'; date: string; data: NonNullable<Narrative['updates']>[number] }
  | { kind: 'catalyst'; date: string; data: Catalyst }

/** Article timeline with interleaved catalyst date markers */
export function TimelineWithMarkers({ updates, connectedCatalysts }: {
  updates: NonNullable<Narrative['updates']>
  connectedCatalysts: Catalyst[]
}) {
  const entries = useMemo<TimelineEntry[]>(() => [
    ...updates.map((update) => ({ kind: 'update' as const, date: update.update_date, data: update })),
    ...connectedCatalysts
      .filter((catalyst) => catalyst.expected_date)
      .map((catalyst) => ({ kind: 'catalyst' as const, date: catalyst.expected_date!, data: catalyst })),
  ].sort((entryA, entryB) => entryA.date.localeCompare(entryB.date)), [updates, connectedCatalysts])

  return (
    <div className="space-y-0">
      {entries.map((entry, entryIndex) => (
        <div key={entry.kind === 'update' ? `u-${entry.data.id}` : `c-${entry.data.id}`} className="flex gap-3 relative">
          {entryIndex < entries.length - 1 && (
            <div className="absolute left-[7px] top-5 bottom-0 w-px bg-border/40" />
          )}
          <div className="relative shrink-0 mt-1">
            {entry.kind === 'update' ? (
              <span className={cn('block h-[9px] w-[9px] rounded-full ring-2 ring-background', SHIFT_DOT[entry.data.sentiment_shift ?? 'neutral'])} />
            ) : (
              <span className="block h-[9px] w-[9px] rounded-sm ring-2 ring-background bg-amber-400" />
            )}
          </div>
          <div className="min-w-0 flex-1 pb-3">
            {entry.kind === 'update' ? (
              <>
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-[11px] font-mono text-muted-foreground/60 shrink-0">{formatMinDate(entry.date)}</span>
                  <ShiftIcon shift={entry.data.sentiment_shift} />
                  <span className="text-[10px] text-muted-foreground/50">{SHIFT_LABEL[entry.data.sentiment_shift ?? 'neutral']}</span>
                </div>
                <p className="text-[12px] text-foreground/80 leading-snug">{entry.data.headline}</p>
              </>
            ) : (
              <>
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-[11px] font-mono text-muted-foreground/60 shrink-0">{formatMinDate(entry.date)}</span>
                  <span className="text-[9px] uppercase tracking-wider font-medium text-amber-400/70">Catalyst</span>
                </div>
                <p className="text-[12px] text-amber-300/80 leading-snug">{entry.data.event}</p>
              </>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

/** Catalyst phases rendered as vertical timeline */
export function PhasesTimeline({ phases }: { phases: Record<string, { period: string; impact: string; behavior: string }> }) {
  const phaseEntries = Object.entries(phases)
  return (
    <div className="space-y-0">
      {phaseEntries.map(([phaseName, phase], phaseIndex) => (
        <div key={phaseName} className="flex gap-3 relative">
          {phaseIndex < phaseEntries.length - 1 && (
            <div className="absolute left-[7px] top-5 bottom-0 w-px bg-border/40" />
          )}
          <div className="relative shrink-0 mt-1">
            <span className="block h-[9px] w-[9px] rounded-sm ring-2 ring-background bg-amber-400/80" />
          </div>
          <div className="min-w-0 flex-1 pb-4">
            <span className="text-[11px] font-medium text-foreground/80 block">{phaseName.replace(/_/g, ' ')}</span>
            <span className="text-[10px] font-mono text-muted-foreground/60 block mb-0.5">{phase.period}</span>
            <p className="text-[11px] text-muted-foreground/50 leading-snug">{phase.impact}</p>
            <p className="text-[11px] text-foreground/60 leading-snug mt-0.5">{phase.behavior}</p>
          </div>
        </div>
      ))}
    </div>
  )
}
