import {
  TrendingDown,
  TrendingUp,
  ArrowDownCircle,
  ArrowUpCircle,
  BarChart3,
} from 'lucide-react'
import { Badge } from '../ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '../ui/tooltip'
import { toTitleCase } from '../../lib/utils'
import { formatPrice } from '../briefing/recommendations/shared'
import type { Alert, AlertAction, AlertCondition, AlertConditionType, DipBuyMetadata } from '../../types/index'
import type { LucideIcon } from 'lucide-react'

// ── Config ──────────────────────────────────────────────────────────────────

export const CONDITION_CONFIG: Record<AlertConditionType, { icon: LucideIcon; className: string; label: string }> = {
  price_below: { icon: TrendingDown, className: 'text-emerald-500', label: 'Price Below' },
  price_above: { icon: TrendingUp, className: 'text-rose-500', label: 'Price Above' },
  rsi_below: { icon: ArrowDownCircle, className: 'text-emerald-500', label: 'RSI Below' },
  rsi_above: { icon: ArrowUpCircle, className: 'text-rose-500', label: 'RSI Above' },
  volume_spike: { icon: BarChart3, className: 'text-amber-500', label: 'Volume Spike' },
}

export const ACTION_COLOR: Record<string, string> = {
  BUY: 'text-emerald-500',
  ADD: 'text-emerald-500',
  EXIT: 'text-rose-500',
  TRIM: 'text-rose-400',
  WATCH: 'text-amber-400',
}

export const PRIORITY_DOT: Record<Alert['priority'], string> = {
  high: 'bg-red-500',
  normal: 'bg-muted-foreground/40',
  low: 'bg-muted-foreground/20',
}

export const PRIORITY_ORDER: Record<Alert['priority'], number> = { high: 0, normal: 1, low: 2 }

export const PRIORITY_CARD_STYLES: Record<Alert['priority'], string> = {
  high: 'bg-red-500/[0.04] border-border',
  normal: '',
  low: 'opacity-80',
}

export const ACTION_BADGE_STYLES: Record<string, string> = {
  BUY: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/25',
  ADD: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/25',
  EXIT: 'bg-rose-500/15 text-rose-400 border-rose-500/25',
  TRIM: 'bg-amber-500/15 text-amber-400 border-amber-500/25',
  WATCH: 'bg-sky-500/15 text-sky-400 border-sky-500/25',
}

/** Auto-suggest action based on primary condition direction */
export const CONDITION_DEFAULT_ACTION: Record<AlertConditionType, AlertAction> = {
  price_below: 'BUY',
  price_above: 'EXIT',
  rsi_below: 'BUY',
  rsi_above: 'TRIM',
  volume_spike: 'WATCH',
}

/** Live preview showing what the condition will look like on the card */
export function ConditionPreview({
  conditions,
}: {
  conditions: { type: AlertConditionType; value: number }[]
}) {
  const firstCondition = conditions?.[0]
  if (!firstCondition?.type || !firstCondition?.value) return null

  const config = CONDITION_CONFIG[firstCondition.type]
  if (!config) return null

  const conditionForPreview = {
    id: 'preview',
    condition_type: firstCondition.type,
    condition_value: firstCondition.value,
    params: {},
    sort_order: 0,
  }

  return (
    <div className="rounded-md bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
      <span className="mr-2">Preview:</span>
      <ConditionChip cond={conditionForPreview} />
    </div>
  )
}

export function sortByPriority(alerts: Alert[]): Alert[] {
  return [...alerts].sort((alertA, alertB) => {
    const priorityDelta = PRIORITY_ORDER[alertA.priority] - PRIORITY_ORDER[alertB.priority]
    if (priorityDelta !== 0) return priorityDelta
    return new Date(alertB.created_at).getTime() - new Date(alertA.created_at).getTime()
  })
}

const SETUP_COLORS: Record<string, string> = {
  CAPITULATION: 'bg-rose-500/15 text-rose-400 border-rose-500/20',
  EXHAUSTION: 'bg-amber-500/15 text-amber-400 border-amber-500/20',
  ORDERLY_DECLINE: 'bg-sky-500/15 text-sky-400 border-sky-500/20',
}

const CONVICTION_DOTS: Record<string, string> = {
  HIGH: 'bg-emerald-500',
  MEDIUM: 'bg-amber-500',
  LOW: 'bg-muted-foreground/40',
}

export function formatConditionValue(cond: AlertCondition) {
  if (cond.condition_value === null) return ''
  return Number(cond.condition_value).toLocaleString('vi-VN')
}

// ── Components ──────────────────────────────────────────────────────────────

export function ConditionChip({
  cond,
  triggeredValue,
}: {
  cond: AlertCondition
  triggeredValue?: number
}) {
  const config = CONDITION_CONFIG[cond.condition_type]
  if (!config) return <span className="text-muted-foreground text-xs">{cond.condition_type}</span>
  const Icon = config.icon
  const valueStr = formatConditionValue(cond)
  const actualStr = triggeredValue != null ? Number(triggeredValue).toLocaleString('vi-VN') : null

  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-muted/40 border border-border/40 px-1.5 py-0.5 text-[11px] font-mono whitespace-nowrap">
      <Icon className={`h-3 w-3 shrink-0 ${config.className}`} />
      <span className="text-foreground/80">{config.label}</span>
      <span className="text-muted-foreground">{valueStr}</span>
      {actualStr && (
        <span className="text-emerald-400 ml-0.5">→ {actualStr}</span>
      )}
    </span>
  )
}

export function ConditionsCell({ alert }: { alert: Alert }) {
  const { conditions, condition_logic, triggered_values } = alert
  if (!conditions || conditions.length === 0) {
    return <span className="text-muted-foreground text-xs">—</span>
  }
  if (conditions.length === 1) {
    const triggeredValue = triggered_values?.[conditions[0].condition_type]
    return <ConditionChip cond={conditions[0]} triggeredValue={triggeredValue} />
  }

  return (
    <div className="flex flex-col gap-0.5">
      {conditions.map((cond, index) => {
        const triggeredValue = triggered_values?.[cond.condition_type]
        return (
          <div key={cond.id} className="flex items-start gap-1">
            {index > 0 && (
              <div className="flex flex-col items-center self-stretch mr-0.5" style={{ width: 16 }}>
                <div className="w-px flex-1 border-l-2 border-dashed border-muted-foreground/20" />
              </div>
            )}
            {index === 0 && <div className="w-4 flex-shrink-0" />}
            <ConditionChip cond={cond} triggeredValue={triggeredValue ?? undefined} />
            {index < conditions.length - 2 && (
              <span className="self-end text-[9px] font-mono text-muted-foreground/50 ml-0.5 pb-0.5">
                {condition_logic}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}

export function TickerCell({ ticker, action }: { ticker: string; action: string | null }) {
  const dotColor = action === 'BUY' || action === 'ADD'
    ? 'bg-emerald-500'
    : action === 'EXIT' || action === 'TRIM'
      ? 'bg-rose-500'
      : 'bg-amber-500'

  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`h-1.5 w-1.5 rounded-full ${dotColor} shrink-0`} />
      <span className="font-mono font-semibold text-sm">{ticker}</span>
    </span>
  )
}

export function DipBuyBadge({ alert }: { alert: Alert }) {
  const meta = alert.alert_metadata as DipBuyMetadata | null
  if (!meta?.setup_id || alert.source !== 'dip_buy') return null

  const setupLabel = toTitleCase(meta.setup_type)
  const colorClass = SETUP_COLORS[meta.setup_type] ?? ''
  const convDot = CONVICTION_DOTS[meta.conviction] ?? ''

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className="inline-flex items-center gap-1.5 cursor-help"
          data-test-id={`dip-buy-badge-${alert.id}`}
        >
          <Badge className={`text-[10px] px-1.5 py-0 h-4 ${colorClass}`}>
            T{meta.tranche}/{meta.total_tranches}
          </Badge>
          <span className={`h-1.5 w-1.5 rounded-full ${convDot} shrink-0`} />
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-[260px] text-xs space-y-1">
        <div className="font-medium">Dip Buy — {setupLabel}</div>
        <div>Tranche {meta.tranche} of {meta.total_tranches} ({meta.pct_of_size}% of position)</div>
        <div>Conviction: {meta.conviction}</div>
        {(alert.entry_price || alert.stop_price || alert.target_price) && (
          <div className="font-mono text-[10px] text-muted-foreground pt-0.5">
            E {formatPrice(alert.entry_price)} / S {formatPrice(alert.stop_price)} / T {formatPrice(alert.target_price)}
          </div>
        )}
      </TooltipContent>
    </Tooltip>
  )
}
