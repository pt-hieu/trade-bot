import { useState, useMemo } from 'react'
import { ChevronDown, Layers, XCircle } from 'lucide-react'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { cn, toTitleCase } from '../../lib/utils'
import { formatRelativeTime, toDateStr, formatShortDate } from '../../lib/date'
import { ConditionChip, ACTION_BADGE_STYLES, PRIORITY_CARD_STYLES } from './components'
import {
  groupByTicker,
  compressSourceDates,
  getTriggeredPrice,
  type TickerGroup,
  type ActionSubGroup,
} from './ticker-stack-utils'
import type { Alert } from '../../types/index'

interface AlertTickerStackProps {
  alerts: Alert[]
  onCancel: (alert: Alert) => void
  isCancelling: boolean
}

export function AlertTickerStack({ alerts, onCancel, isCancelling }: AlertTickerStackProps) {
  const groups = useMemo(() => groupByTicker(alerts), [alerts])

  return (
    <div className="space-y-2">
      {groups.map((group) => (
        <TickerRow
          key={group.ticker}
          group={group}
          onCancel={onCancel}
          isCancelling={isCancelling}
        />
      ))}
    </div>
  )
}

function TickerRow({
  group,
  onCancel,
  isCancelling,
}: {
  group: TickerGroup
  onCancel: (alert: Alert) => void
  isCancelling: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const { ticker, highestPriority, actionSubGroups, totalCount, anyConditionLive } = group
  const isHigh = highestPriority === 'high'
  const hasMultiple = totalCount > 1
  const primarySubGroup = actionSubGroups[0]
  const isDead = anyConditionLive === false

  return (
    <div
      className={cn(
        'rounded-lg border border-border/60 overflow-hidden transition-colors',
        PRIORITY_CARD_STYLES[highestPriority],
        expanded && 'bg-muted/[0.03] border-border',
        isDead && 'opacity-50',
      )}
    >
      <button
        onClick={() => hasMultiple && setExpanded(!expanded)}
        className={cn(
          'w-full flex items-center gap-3 px-4 py-3 text-left transition-colors',
          hasMultiple ? 'cursor-pointer hover:bg-muted/20' : 'cursor-default',
        )}
      >
        {hasMultiple ? (
          <ChevronDown
            className={cn(
              'h-4 w-4 text-muted-foreground shrink-0 transition-transform',
              !expanded && '-rotate-90',
            )}
          />
        ) : (
          <div className="w-4 shrink-0" />
        )}

        <span
          className={cn(
            'font-mono shrink-0',
            isHigh ? 'text-2xl font-black tracking-tight' : 'text-lg font-bold',
          )}
        >
          {ticker}
        </span>

        {actionSubGroups.map((subGroup) =>
          subGroup.action ? (
            <Badge
              key={subGroup.action}
              variant="outline"
              className={cn(
                'text-xs font-semibold px-2 shrink-0',
                ACTION_BADGE_STYLES[subGroup.action] || '',
              )}
            >
              {subGroup.action}
              {subGroup.alerts.length > 1 && (
                <span className="ml-1 opacity-60">×{subGroup.alerts.length}</span>
              )}
            </Badge>
          ) : null,
        )}

        {isHigh && (
          <span className="text-[10px] font-medium text-red-400 uppercase tracking-wide shrink-0">
            High
          </span>
        )}

        <div className="flex-1 flex items-center gap-2 min-w-0">
          {primarySubGroup?.alerts[0]?.conditions[0] && (
            <ConditionChip cond={primarySubGroup.alerts[0].conditions[0]} />
          )}
          <PriceIndicator
            price={primarySubGroup?.latestTriggeredPrice}
            conditionStillMet={primarySubGroup?.conditionStillMet}
          />
        </div>

        {actionSubGroups.some((subGroup) => subGroup.uniqueSources.length > 1) && (
          <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400/80 shrink-0">
            <Layers className="h-3 w-3" />
            Multi-source
          </span>
        )}

        <span className="text-xs text-muted-foreground shrink-0">
          {primarySubGroup?.alerts[0]?.triggered_at
            ? formatRelativeTime(primarySubGroup.alerts[0].triggered_at)
            : formatRelativeTime(primarySubGroup?.alerts[0]?.created_at)}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-border/30">
          {actionSubGroups.map((subGroup) => (
            <ActionSubGroupView
              key={subGroup.action || '_none'}
              subGroup={subGroup}
              showActionHeader={actionSubGroups.length > 1}
              onCancel={onCancel}
              isCancelling={isCancelling}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function PriceIndicator({
  price,
  conditionStillMet,
}: {
  price: number | null | undefined
  conditionStillMet: boolean | null | undefined
}) {
  if (price == null) return null
  const formattedPrice = Number(price).toLocaleString('vi-VN')
  const colorClass =
    conditionStillMet === true
      ? 'text-emerald-400'
      : conditionStillMet === false
        ? 'text-rose-400/70 line-through'
        : 'text-muted-foreground'

  return (
    <span className={cn('text-[11px] font-mono shrink-0', colorClass)}>
      now {formattedPrice}
    </span>
  )
}

function ActionSubGroupView({
  subGroup,
  showActionHeader,
  onCancel,
  isCancelling,
}: {
  subGroup: ActionSubGroup
  showActionHeader: boolean
  onCancel: (alert: Alert) => void
  isCancelling: boolean
}) {
  const { action, alerts: subAlerts, isDuplicated } = subGroup

  return (
    <div>
      {showActionHeader && action && (
        <div className="px-4 py-1.5 pl-12 bg-muted/10 flex items-center gap-2">
          <span
            className={cn(
              'text-[11px] font-mono font-semibold',
              action in ACTION_BADGE_STYLES
                ? ACTION_BADGE_STYLES[action].split(' ').find((className) => className.startsWith('text-'))
                : 'text-muted-foreground',
            )}
          >
            {action}
          </span>
          <span className="text-[10px] text-muted-foreground">
            {subAlerts.length} occurrence{subAlerts.length > 1 ? 's' : ''}
          </span>
        </div>
      )}

      {isDuplicated && (
        <div className="px-4 py-2 pl-12 flex items-center justify-between">
          <span className="text-[11px] text-muted-foreground">
            Same signal — {compressSourceDates(subAlerts)}
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-[11px] text-muted-foreground hover:text-destructive shrink-0"
            onClick={() => onCancel(subAlerts[0])}
            disabled={isCancelling}
          >
            <XCircle className="h-3 w-3 mr-1" />
            Dismiss duplicates
          </Button>
        </div>
      )}

      {!isDuplicated &&
        subAlerts.map((alert, index) => (
          <TriggerEventRow
            key={alert.id}
            alert={alert}
            isEven={index % 2 === 0}
            onCancel={onCancel}
            isCancelling={isCancelling}
          />
        ))}
    </div>
  )
}

function TriggerEventRow({
  alert,
  isEven,
  onCancel,
  isCancelling,
}: {
  alert: Alert
  isEven: boolean
  onCancel: (alert: Alert) => void
  isCancelling: boolean
}) {
  const sourceDate = formatShortDate(toDateStr(alert.source_date))
  const sourceLabel = toTitleCase(alert.source)
  const triggeredPrice = getTriggeredPrice(alert)

  return (
    <div
      className={cn(
        'flex items-center gap-3 px-4 py-2.5 pl-12',
        isEven ? 'bg-muted/5' : '',
      )}
    >
      <span
        className="text-[11px] text-muted-foreground shrink-0 w-40 truncate"
        title={`${sourceLabel} · ${sourceDate}`}
      >
        {sourceLabel} · {sourceDate}
      </span>

      <div className="flex-1 flex items-center gap-2 min-w-0">
        {alert.conditions[0] && (
          <ConditionChip cond={alert.conditions[0]} />
        )}
        {triggeredPrice != null && (
          <span className="text-[10px] font-mono text-muted-foreground">
            at {Number(triggeredPrice).toLocaleString('vi-VN')}
          </span>
        )}
      </div>

      {alert.entry_price != null && (
        <span className="text-[11px] font-mono text-muted-foreground shrink-0">
          Entry {Number(alert.entry_price).toLocaleString('vi-VN')}
        </span>
      )}

      <span className="text-[10px] text-muted-foreground shrink-0 w-16 text-right font-mono">
        {alert.triggered_at
          ? formatRelativeTime(alert.triggered_at)
          : formatRelativeTime(alert.created_at)}
      </span>

      <Button
        variant="ghost"
        size="sm"
        className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive shrink-0"
        onClick={() => onCancel(alert)}
        disabled={isCancelling}
      >
        <XCircle className="h-3.5 w-3.5" />
      </Button>
    </div>
  )
}
