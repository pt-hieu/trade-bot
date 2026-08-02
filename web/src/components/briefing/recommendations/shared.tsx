import { Badge } from '../../ui/badge'
import {
  TableCell,
} from '../../ui/table'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '../../ui/tooltip'
import { Bell, Zap, BellOff } from 'lucide-react'
import { toTitleCase, formatVNDK } from '../../../lib/utils'
import type { Recommendation, RecAction, RecAlert, EvalStatus } from '../../../types/index'
import type { DipBuyMetadata } from '../../../types/index'

// ── Config ───────────────────────────────────────────────────────────────────

export const ACTION_COLORS: Record<RecAction, string> = {
  BUY: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
  LIMIT_BUY: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
  ADD: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
  SELL: 'bg-rose-500/15 text-rose-400 border-rose-500/20',
  EXIT: 'bg-rose-500/15 text-rose-400 border-rose-500/20',
  TRIM: 'bg-orange-500/15 text-orange-400 border-orange-500/20',
  HOLD: 'bg-amber-500/15 text-amber-400 border-amber-500/20',
  WATCH: 'bg-sky-500/15 text-sky-400 border-sky-500/20',
  WAIT: 'bg-muted text-muted-foreground border-border',
  SKIP: 'bg-muted text-muted-foreground border-border',
  AVOID: 'bg-rose-500/10 text-rose-300 border-rose-500/15',
}

export const EVAL_COLORS: Partial<Record<EvalStatus, string>> = {
  WIN: 'text-emerald-400',
  LOSS: 'text-rose-400',
  PENDING: 'text-muted-foreground',
  MISSED: 'text-muted-foreground',
}

export const ROW_BORDERS: Partial<Record<EvalStatus, string>> = {
  WIN: 'bg-emerald-500/5',
  LOSS: 'bg-rose-500/5',
}

export const SECTION_LABELS: Record<string, string> = {
  MY_HOLDINGS: 'My holdings',
  TOP_PICKS: 'Top picks',
  LONG_TERM: 'Long-term',
  SKIP_THESE: 'Skip these',
  OTHER: 'Other',
}

export type SectionKey = 'MY_HOLDINGS' | 'TOP_PICKS' | 'LONG_TERM' | 'SKIP_THESE' | 'OTHER'

// ── Helpers ──────────────────────────────────────────────────────────────────

/** @deprecated Use formatVNDK from @/lib/utils instead */
export const formatPrice = formatVNDK

export function calcRR(entry: number | null, stop: number | null, target: number | null) {
  if (!entry || !stop || !target) return null
  const risk = Math.abs(Number(entry) - Number(stop))
  if (risk === 0) return null
  const reward = Math.abs(Number(target) - Number(entry))
  return (reward / risk).toFixed(1)
}

// ── Reusable components ──────────────────────────────────────────────────────

export { ColumnInfo } from '../../ui/column-info'
export { CardLabel } from '../../ui/card-label'

export function TickerCell({ ticker }: { ticker: string }) {
  return <TableCell className="font-mono font-semibold align-top">{ticker}</TableCell>
}

export function ActionCell({ action }: { action: RecAction }) {
  return (
    <TableCell className="align-top">
      <Badge className={`text-xs ${ACTION_COLORS[action]}`}>{toTitleCase(action)}</Badge>
    </TableCell>
  )
}

export function RationaleCell({ rationale }: { rationale: string | null }) {
  return (
    <TableCell className="text-xs text-muted-foreground align-top">
      <span className="line-clamp-2 whitespace-normal break-words">{rationale || '—'}</span>
    </TableCell>
  )
}

export function EodCell({ evaluation }: { evaluation: Recommendation['evaluation'] }) {
  return (
    <TableCell className="text-right font-mono tabular-nums text-xs">
      {evaluation?.eod_price_vnd ? formatPrice(evaluation.eod_price_vnd) : '—'}
    </TableCell>
  )
}

export function ResultCell({ evaluation }: { evaluation: Recommendation['evaluation'] }) {
  const evalStatus = evaluation?.status
  return (
    <TableCell className="text-right">
      {evalStatus ? (
        <span className={`text-xs font-mono font-medium ${EVAL_COLORS[evalStatus] ?? 'text-muted-foreground'}`}>
          {toTitleCase(evalStatus)}
        </span>
      ) : (
        <span className="text-xs text-zinc-500">—</span>
      )}
    </TableCell>
  )
}

export function PnlCell({ evaluation }: { evaluation: Recommendation['evaluation'] }) {
  return (
    <TableCell className="text-right">
      {evaluation?.pnl_percent != null ? (
        <span className={`text-xs font-mono tabular-nums ${Number(evaluation.pnl_percent) > 0 ? 'text-emerald-400' : Number(evaluation.pnl_percent) < 0 ? 'text-rose-400' : 'text-muted-foreground'}`}>
          {Number(evaluation.pnl_percent) > 0 ? '+' : ''}{Number(evaluation.pnl_percent).toFixed(1)}%
        </span>
      ) : (
        <span className="text-xs text-zinc-500">—</span>
      )}
    </TableCell>
  )
}

// ── Alert Cell ──────────────────────────────────────────────────────────────

const CONDITION_LABELS: Record<string, string> = {
  price_below: '<',
  price_above: '>',
  rsi_below: 'RSI <',
  rsi_above: 'RSI >',
  volume_spike: 'Vol ≥',
}

const SOURCE_LABELS: Record<string, string> = {
  morning_brief: 'AM',
  midday: 'MD',
  position_monitor: 'POS',
  longterm: 'LT',
  dip_buy: 'DIP',
}

function formatAlertValue(type: string, value: number | null) {
  if (value == null) return ''
  if (type.startsWith('price_')) return formatVNDK(value)
  if (type.startsWith('rsi_')) return value.toFixed(0)
  return `${value}x`
}

import { formatRelativeTime } from '../../../lib/date'

function dipSuffix(meta: DipBuyMetadata | null | undefined) {
  if (!meta?.setup_id) return ''
  const setup = meta.setup_type === 'ORDERLY_DECLINE' ? 'Decline' : meta.setup_type.charAt(0) + meta.setup_type.slice(1).toLowerCase()
  return ` — T${meta.tranche}/${meta.total_tranches} ${setup} (${meta.conviction})`
}

function AlertBadge({ alert }: { alert: RecAlert }) {
  const label = CONDITION_LABELS[alert.condition_type] ?? alert.condition_type
  const value = formatAlertValue(alert.condition_type, alert.condition_value)
  const srcLabel = SOURCE_LABELS[alert.source] ?? alert.source
  const meta = alert.alert_metadata as DipBuyMetadata | null

  if (alert.status === 'cancelled') return null

  if (alert.status === 'triggered') {
    const trigVal = formatAlertValue(alert.condition_type, alert.triggered_value)
    const ago = alert.triggered_at ? formatRelativeTime(alert.triggered_at) : ''
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex items-center gap-1 text-emerald-400 cursor-help">
            <Zap className="h-3 w-3 shrink-0" />
            <span className="text-xs font-mono">{trigVal}</span>
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[240px] text-xs">
          <span className="font-medium">Triggered</span> {ago} at {trigVal} (condition: {label} {value}, source: {srcLabel}{dipSuffix(meta)})
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
        <TooltipContent side="top" className="max-w-[240px] text-xs">Expired — {label} {value} not met ({srcLabel}{dipSuffix(meta)})</TooltipContent>
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
          {meta?.setup_id && (
            <span className="text-xs text-muted-foreground font-mono">T{meta.tranche}/{meta.total_tranches}</span>
          )}
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-[240px] text-xs">
        Active: {label} {value} ({srcLabel}{dipSuffix(meta)}, {alert.priority})
      </TooltipContent>
    </Tooltip>
  )
}

export function AlertCell({ alerts }: { alerts: RecAlert[] }) {
  const visible = alerts.filter((a) => a.status !== 'cancelled')

  if (visible.length === 0) {
    return (
      <TableCell className="text-center">
        <span className="text-xs text-zinc-600">—</span>
      </TableCell>
    )
  }

  return (
    <TableCell className="text-center">
      <div className="flex flex-col items-center gap-0.5">
        {visible.map((a) => (
          <AlertBadge key={a.id} alert={a} />
        ))}
      </div>
    </TableCell>
  )
}
