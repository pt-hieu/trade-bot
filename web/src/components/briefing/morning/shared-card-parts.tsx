import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { ArrowRight, Eye, Bell, Zap, BellOff, ChevronRight } from 'lucide-react'
import { Badge } from '../../ui/badge'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '../../ui/collapsible'
import { Tooltip, TooltipContent, TooltipTrigger } from '../../ui/tooltip'
import { cn, toTitleCase, formatVNDK } from '../../../lib/utils'
import { formatRelativeTime } from '../../../lib/date'
import type { Recommendation, RecAction, RecAlert, EvalStatus } from '../../../types/intel'
import { ACTION_COLORS, EVAL_COLORS } from '../recommendations/shared'

// ── Alert constants ───────────────────────────────────────────────────────────

export const CONDITION_LABELS: Record<string, string> = {
  price_below: '<',
  price_above: '>',
  rsi_below: 'RSI <',
  rsi_above: 'RSI >',
  volume_spike: 'Vol ≥',
}

export const SOURCE_LABELS: Record<string, string> = {
  morning_brief: 'AM',
  midday: 'MD',
  position_monitor: 'POS',
  longterm: 'LT',
  dip_buy: 'DIP',
}

export function formatAlertValue(conditionType: string, value: number | null): string {
  if (value == null) return ''
  if (conditionType.startsWith('price_')) return formatVNDK(value)
  if (conditionType.startsWith('rsi_')) return value.toFixed(0)
  return `${value}x`
}

// ── CardAlert ─────────────────────────────────────────────────────────────────

export function CardAlert({ alert }: { alert: RecAlert }) {
  const label = CONDITION_LABELS[alert.condition_type] ?? alert.condition_type
  const value = formatAlertValue(alert.condition_type, alert.condition_value)
  const sourceLabel = SOURCE_LABELS[alert.source] ?? alert.source

  if (alert.status === 'cancelled') return null

  if (alert.status === 'triggered') {
    const triggeredValue = formatAlertValue(alert.condition_type, alert.triggered_value)
    const timeAgo = alert.triggered_at ? formatRelativeTime(alert.triggered_at) : ''
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex items-center gap-1 text-emerald-400 cursor-help">
            <Zap className="h-3 w-3 shrink-0" />
            <span className="text-xs font-mono">{triggeredValue}</span>
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[240px] text-xs">
          <span className="font-medium">Triggered</span> {timeAgo} at {triggeredValue} (condition: {label} {value}, source: {sourceLabel})
        </TooltipContent>
      </Tooltip>
    )
  }

  if (alert.status === 'expired') {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex items-center gap-1 text-zinc-600 cursor-help">
            <BellOff className="h-3 w-3 shrink-0" />
            <span className="text-xs font-mono line-through">{value}</span>
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[240px] text-xs">
          Expired — {label} {value} not met ({sourceLabel})
        </TooltipContent>
      </Tooltip>
    )
  }

  // active
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex items-center gap-1 text-amber-400 cursor-help">
          <Bell className="h-3 w-3 shrink-0 animate-pulse" />
          <span className="text-xs font-mono">{label} {value}</span>
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-[240px] text-xs">
        Active: {label} {value} ({sourceLabel}, {alert.priority})
      </TooltipContent>
    </Tooltip>
  )
}

// ── Conviction helpers ────────────────────────────────────────────────────────

export type ConvictionTier = 'high' | 'medium' | 'low'

export function getConvictionTier(confidence: number | null): ConvictionTier {
  if (confidence == null || confidence < 0.6) return 'low'
  if (confidence < 0.8) return 'medium'
  return 'high'
}

export const CONVICTION_DOT_CLASS: Record<ConvictionTier, string> = {
  high: 'bg-emerald-400',
  medium: 'bg-amber-400',
  low: 'bg-zinc-600',
}

export const CONVICTION_LABEL: Record<ConvictionTier, string> = {
  high: 'High',
  medium: 'Med',
  low: 'Low',
}

export function ConvictionDot({ confidence }: { confidence: number | null }) {
  const tier = getConvictionTier(confidence)
  const dotClass = CONVICTION_DOT_CLASS[tier]
  const label = CONVICTION_LABEL[tier]

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex items-center gap-1 cursor-help">
          <span className={cn('h-1.5 w-1.5 rounded-full shrink-0', dotClass)} />
          <span className="text-xs text-muted-foreground">{label}</span>
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" className="text-xs">
        Conviction: {label}{confidence != null ? ` (${(confidence * 100).toFixed(0)}%)` : ''}
      </TooltipContent>
    </Tooltip>
  )
}

// ── CTA ───────────────────────────────────────────────────────────────────────

export function RecCardCta({ rec }: { rec: Recommendation }) {
  const action = rec.action

  if (action === 'BUY' || action === 'ADD' || action === 'LIMIT_BUY') {
    return (
      <Link
        to="/trades"
        search={{ ticker: rec.ticker, strategy: rec.strategy ?? undefined } as any}
        className="inline-flex items-center gap-1 text-xs font-medium text-emerald-400 hover:text-emerald-300 transition-colors cursor-pointer"
      >
        Execute <ArrowRight className="h-3 w-3" />
      </Link>
    )
  }

  if (action === 'EXIT' || action === 'TRIM' || action === 'SELL') {
    return (
      <Link
        to="/trades"
        search={{ ticker: rec.ticker } as any}
        className="inline-flex items-center gap-1 text-xs font-medium text-rose-400 hover:text-rose-300 transition-colors cursor-pointer"
      >
        Execute <ArrowRight className="h-3 w-3" />
      </Link>
    )
  }

  if (action === 'WATCH') {
    return (
      <Link
        to="/watchlist"
        search={{ add: rec.ticker } as any}
        className="inline-flex items-center gap-1 text-xs font-medium text-sky-400 hover:text-sky-300 transition-colors cursor-pointer"
      >
        Watch <Eye className="h-3 w-3" />
      </Link>
    )
  }

  return null
}

// ── Eval card background ──────────────────────────────────────────────────────

/** Card bg tinted by P/L magnitude — stronger color for bigger moves */
export function evalCardBackground(
  evalStatus: EvalStatus | null | undefined,
  pnlPercent?: number | null,
): string {
  const absPnl = pnlPercent != null ? Math.abs(pnlPercent) : 0

  if (evalStatus === 'WIN' || (pnlPercent != null && pnlPercent > 0)) {
    if (absPnl >= 5) return 'bg-emerald-500/10'
    if (absPnl >= 2) return 'bg-emerald-500/[0.07]'
    return 'bg-emerald-500/[0.04]'
  }
  if (evalStatus === 'LOSS' || (pnlPercent != null && pnlPercent < 0)) {
    if (absPnl >= 5) return 'bg-rose-500/10'
    if (absPnl >= 2) return 'bg-rose-500/[0.07]'
    return 'bg-rose-500/[0.04]'
  }
  return 'bg-card/50'
}

// ── Rationale collapsible ─────────────────────────────────────────────────────

interface RationaleCollapsibleProps {
  rationale: string | null | undefined
  /** Override toggle label (default: "rationale") */
  label?: string
  /** Additional class for the expanded text */
  className?: string
}

export function RationaleCollapsible({ rationale, label, className }: RationaleCollapsibleProps) {
  const [isOpen, setIsOpen] = useState(false)
  const displayLabel = label ?? 'rationale'

  if (!rationale) return null

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <button className="flex items-center gap-1.5 text-left group cursor-pointer">
          <ChevronRight
            className={cn(
              'h-3 w-3 text-zinc-500 transition-transform duration-200 shrink-0',
              isOpen && 'rotate-90',
            )}
          />
          <span className={cn(
            'text-xs group-hover:text-muted-foreground transition-colors',
            className ?? 'text-zinc-400',
          )}>
            {displayLabel}
          </span>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <p className={cn('mt-1.5 text-xs leading-relaxed pl-4', className ?? 'text-muted-foreground')}>
          {rationale}
        </p>
      </CollapsibleContent>
    </Collapsible>
  )
}

// ── Inline rationale (for short content that doesn't need a toggle) ──────────

const SHORT_RATIONALE_THRESHOLD = 120

export function InlineRationale({ rationale }: { rationale: string | null | undefined }) {
  if (!rationale) return null

  // Short rationale → show inline, no toggle
  if (rationale.length <= SHORT_RATIONALE_THRESHOLD) {
    return (
      <p className="text-xs text-muted-foreground leading-relaxed">
        {rationale}
      </p>
    )
  }

  return <RationaleCollapsible rationale={rationale} />
}

// Re-export shared colors for consumers that only need card-level imports
export { ACTION_COLORS, EVAL_COLORS }
export type { RecAction, EvalStatus }
