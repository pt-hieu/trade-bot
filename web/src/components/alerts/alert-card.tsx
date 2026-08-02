import { Pencil, XCircle, Repeat } from 'lucide-react'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { cn } from '../../lib/utils'
import { formatRelativeTime } from '../../lib/date'
import {
  ConditionsCell,
  DipBuyBadge,
  ACTION_BADGE_STYLES,
  PRIORITY_CARD_STYLES,
} from './components'
import type { Alert, DipBuyMetadata } from '../../types/index'


interface AlertCardProps {
  alert: Alert
  repeatCount?: number
  onEdit: (alert: Alert) => void
  onCancel: (alert: Alert) => void
  isCancelling: boolean
}

export function AlertCard({ alert, repeatCount, onEdit, onCancel, isCancelling }: AlertCardProps) {
  const priorityStyle = PRIORITY_CARD_STYLES[alert.priority]
  const isTriggered = alert.status === 'triggered'
  const isDipBuy = alert.source === 'dip_buy'
  const isHigh = alert.priority === 'high'
  const isRepeated = (repeatCount || 0) > 1

  return (
    <div
      className={cn(
        'rounded-lg border border-border/60 p-4 transition-colors hover:border-border',
        priorityStyle,
        isTriggered && 'ring-1 ring-amber-500/20',
      )}
    >
      {/* Top row: ticker + action + meta + time */}
      <div className="flex items-center gap-2.5 mb-3">
        {/* Ticker — dominant on HIGH cards, standard on others */}
        <span
          className={cn(
            'font-mono',
            isHigh
              ? 'text-2xl font-black tracking-tight'
              : 'text-base font-bold',
          )}
        >
          {alert.ticker}
        </span>

        {alert.recommended_action && (
          <Badge
            variant="outline"
            className={cn(
              'text-xs font-semibold px-2',
              ACTION_BADGE_STYLES[alert.recommended_action] || '',
            )}
          >
            {alert.recommended_action}
          </Badge>
        )}

        {isTriggered && (
          <Badge className="bg-amber-500/15 text-amber-400 border border-amber-500/25 text-[10px] px-1.5">
            Triggered
          </Badge>
        )}

        {isHigh && (
          <span className="text-[10px] font-medium text-red-400 uppercase tracking-wide">
            High
          </span>
        )}

        {/* Repeated ticker signal */}
        {isRepeated && (
          <span className="inline-flex items-center gap-1 text-[10px] text-amber-400/80">
            <Repeat className="h-3 w-3" />
            {repeatCount}x this week
          </span>
        )}

        <DipBuyBadge alert={alert} />

        <span className="ml-auto text-xs text-muted-foreground shrink-0">
          {isTriggered && alert.triggered_at
            ? `Triggered ${formatRelativeTime(alert.triggered_at)}`
            : formatRelativeTime(alert.created_at)}
        </span>
      </div>

      {/* Body — varies by alert type */}
      {isDipBuy ? (
        <DipBuyCardBody alert={alert} />
      ) : (
        <GeneralCardBody alert={alert} />
      )}

      <PriceLevels
        entryPrice={alert.entry_price}
        stopPrice={alert.stop_price}
        targetPrice={alert.target_price}
      />

      {alert.status === 'active' && (
        <CardActions
          alert={alert}
          onEdit={onEdit}
          onCancel={onCancel}
          isCancelling={isCancelling}
        />
      )}
    </div>
  )
}

// ── Card body variants ───────────────────────────────────────────────────

function GeneralCardBody({ alert }: { alert: Alert }) {
  return (
    <div className="space-y-2">
      <ConditionsCell alert={alert} />
      {alert.rationale && (
        <p className="text-xs text-muted-foreground line-clamp-2">
          {alert.rationale}
        </p>
      )}
    </div>
  )
}

function DipBuyCardBody({ alert }: { alert: Alert }) {
  const metadata = alert.alert_metadata as DipBuyMetadata | null
  return (
    <div className="space-y-2">
      <ConditionsCell alert={alert} />
      {metadata && (
        <div className="flex items-center gap-3 text-xs">
          <span className="text-muted-foreground">
            Tranche <span className="text-foreground font-medium">{metadata.tranche}/{metadata.total_tranches}</span>
          </span>
          <span className="text-muted-foreground">
            Size <span className="text-foreground font-medium">{metadata.pct_of_size}%</span>
          </span>
          <span className="text-muted-foreground">
            Conviction <span className="text-foreground font-medium">{metadata.conviction}</span>
          </span>
        </div>
      )}
      {alert.rationale && (
        <p className="text-xs text-muted-foreground line-clamp-2">
          {alert.rationale}
        </p>
      )}
    </div>
  )
}

// ── Price levels — only show values that exist ───────────────────────────

function PriceLevels({
  entryPrice,
  stopPrice,
  targetPrice,
}: {
  entryPrice: number | null
  stopPrice: number | null
  targetPrice: number | null
}) {
  const hasAnyPrice = entryPrice != null || stopPrice != null || targetPrice != null
  if (!hasAnyPrice) return null

  const formatPrice = (value: number) => Number(value).toLocaleString('vi-VN')

  return (
    <div className="flex items-center gap-4 mt-3 pt-3 border-t border-border/30 text-xs font-mono">
      {entryPrice != null && (
        <span className="text-muted-foreground">
          Entry <span className="text-foreground">{formatPrice(entryPrice)}</span>
        </span>
      )}
      {stopPrice != null && (
        <span className="text-muted-foreground">
          Stop <span className="text-rose-400">{formatPrice(stopPrice)}</span>
        </span>
      )}
      {targetPrice != null && (
        <span className="text-muted-foreground">
          Target <span className="text-emerald-400">{formatPrice(targetPrice)}</span>
        </span>
      )}
    </div>
  )
}

// ── Inline actions — visible, labeled buttons ────────────────────────────

function CardActions({
  alert,
  onEdit,
  onCancel,
  isCancelling,
}: {
  alert: Alert
  onEdit: (alert: Alert) => void
  onCancel: (alert: Alert) => void
  isCancelling: boolean
}) {
  return (
    <div className="flex items-center gap-2 mt-3 pt-3 border-t border-border/30">
      <Button
        variant="outline"
        size="sm"
        className="h-7 text-xs"
        onClick={() => onEdit(alert)}
      >
        <Pencil className="h-3 w-3 mr-1" />
        Edit
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="h-7 text-xs text-muted-foreground hover:text-destructive"
        onClick={() => onCancel(alert)}
        disabled={isCancelling}
      >
        <XCircle className="h-3 w-3 mr-1" />
        Dismiss
      </Button>
    </div>
  )
}
