import type { ReactNode } from 'react'
import { Badge } from '../../ui/badge'
import { cn, toTitleCase, formatVNDK } from '../../../lib/utils'
import { calcRR } from '../recommendations/shared'
import { ACTION_COLORS } from './shared-card-parts'
import type { VerdictData, VerdictTone, ActionItem } from './derive-verdict'

// ── Highlight numbers/percentages in summary text ──────────────────────────

const NUMBER_PATTERN = /([+-]?\d+[\d,.]*[kKmMbB]?%?)/g

function highlightNumbers(text: string): ReactNode[] {
  const parts = text.split(NUMBER_PATTERN)
  return parts.map((part, index) => {
    if (NUMBER_PATTERN.test(part)) {
      // Reset lastIndex since we're using global regex
      NUMBER_PATTERN.lastIndex = 0
      const isNegative = part.startsWith('-')
      const isPositive = part.startsWith('+')
      const colorClass = isNegative
        ? 'text-rose-400'
        : isPositive
          ? 'text-emerald-400'
          : 'text-foreground'
      return (
        <span key={index} className={cn('font-semibold font-mono', colorClass)}>
          {part}
        </span>
      )
    }
    return part
  })
}

// ── Tone visuals ────────────────────────────────────────────────────────────

const TONE_STYLE: Record<VerdictTone, { bg: string; border: string; accent: string }> = {
  defensive: {
    bg: 'bg-rose-500/[0.04]',
    border: 'border-rose-500/20',
    accent: 'text-rose-400',
  },
  offensive: {
    bg: 'bg-emerald-500/[0.04]',
    border: 'border-emerald-500/20',
    accent: 'text-emerald-400',
  },
  steady: {
    bg: 'bg-card/50',
    border: 'border-border/50',
    accent: 'text-muted-foreground',
  },
}

const TRADING_MODE_STYLE: Record<string, string> = {
  LOW_CASH: 'bg-amber-500/15 text-amber-400 border-amber-500/20',
  REALLOCATION: 'bg-rose-500/15 text-rose-400 border-rose-500/20',
}

// ── Action row ──────────────────────────────────────────────────────────────

function ActionRow({ item }: { item: ActionItem }) {
  const rr = calcRR(item.entryPriceVnd, item.stopPriceVnd, item.targetPriceVnd)

  return (
    <div className="flex items-center gap-2 py-1 flex-wrap">
      <Badge className={cn('text-xs shrink-0', ACTION_COLORS[item.action])}>
        {toTitleCase(item.action)}
      </Badge>

      <span className="font-mono font-bold text-sm tracking-tight">{item.ticker}</span>

      {/* Price levels */}
      <div className="flex items-center gap-2 font-mono tabular-nums text-xs">
        {item.entryPriceVnd && (
          <span className="text-zinc-300">@ {formatVNDK(item.entryPriceVnd)}</span>
        )}
        {item.targetPriceVnd && (
          <span className="text-emerald-500">→ {formatVNDK(item.targetPriceVnd)}</span>
        )}
        {item.stopPriceVnd && (
          <span className="text-rose-500">✕ {formatVNDK(item.stopPriceVnd)}</span>
        )}
        {rr && (
          <span className="text-zinc-500">R:R {rr}</span>
        )}
      </div>
    </div>
  )
}

// ── Section ─────────────────────────────────────────────────────────────────

interface VerdictSectionProps {
  verdict: VerdictData
}

export function VerdictSection({ verdict }: VerdictSectionProps) {
  const tone = TONE_STYLE[verdict.tone]
  const hasActions = verdict.actionItems.length > 0
  const modeStyle = verdict.tradingMode ? TRADING_MODE_STYLE[verdict.tradingMode] : null

  return (
    <div className={cn('rounded-xl border px-3 py-2.5 space-y-2', tone.bg, tone.border)}>
      {/* Header: mode badge + counts inline with summary */}
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            {modeStyle && (
              <Badge className={cn('text-xs', modeStyle)}>
                {toTitleCase(verdict.tradingMode!)}
              </Badge>
            )}
            {verdict.holdCount > 0 && (
              <span className="text-xs text-zinc-500 font-mono">
                {verdict.holdCount} hold{verdict.holdCount !== 1 ? 's' : ''}
              </span>
            )}
            {verdict.watchCount > 0 && (
              <span className="text-xs text-zinc-500 font-mono">
                {verdict.watchCount} watching
              </span>
            )}
          </div>
          <p className="text-sm leading-snug text-zinc-100">
            {highlightNumbers(verdict.summary)}
          </p>
        </div>
      </div>

      {/* Action items — tighter rows */}
      {hasActions && (
        <div className="border-t border-border/30 pt-1.5">
          {verdict.actionItems.map((item) => (
            <ActionRow key={`${item.ticker}-${item.action}`} item={item} />
          ))}
        </div>
      )}
    </div>
  )
}
