import { useState, useMemo } from 'react'
import { ChevronDown, Trash2 } from 'lucide-react'
import { Button } from '../ui/button'
import { cn, toTitleCase } from '../../lib/utils'
import { toDateStr, formatShortDate, formatRelativeTime } from '../../lib/date'
import { ConditionChip, ACTION_COLOR } from './components'
import type { Alert } from '../../types/index'

interface AlertHistorySectionProps {
  alerts: Alert[]
  onBulkCancel: (ids: string[]) => void
  isBulkCancelling: boolean
}

interface DateGroup {
  label: string
  alerts: Alert[]
}

function groupByDateAndSource(alerts: Alert[]): DateGroup[] {
  const groups = new Map<string, Alert[]>()
  for (const alert of alerts) {
    const dateKey = toDateStr(alert.source_date)
    const sourceKey = `${dateKey}::${alert.source}`
    const existing = groups.get(sourceKey) || []
    existing.push(alert)
    groups.set(sourceKey, existing)
  }
  return Array.from(groups.entries()).map(([key, groupAlerts]) => {
    const [dateKey, source] = key.split('::')
    const dateLabel = formatShortDate(dateKey)
    const sourceLabel = toTitleCase(source)
    const cancelledInGroup = groupAlerts.filter((alert) => alert.status === 'cancelled').length
    const expiredInGroup = groupAlerts.filter((alert) => alert.status === 'expired').length
    const statusParts: string[] = []
    if (cancelledInGroup > 0) statusParts.push(`${cancelledInGroup} cancelled`)
    if (expiredInGroup > 0) statusParts.push(`${expiredInGroup} expired`)
    const statusSuffix = statusParts.length > 0 ? ` · ${statusParts.join(', ')}` : ''

    return {
      label: `${dateLabel} — ${sourceLabel}${statusSuffix}`,
      alerts: groupAlerts,
    }
  })
}

export function AlertHistorySection({
  alerts,
  onBulkCancel,
  isBulkCancelling,
}: AlertHistorySectionProps) {
  const [expanded, setExpanded] = useState(false)

  const dateGroups = useMemo(() => groupByDateAndSource(alerts), [alerts])

  if (alerts.length === 0) return null

  const cancelledCount = alerts.filter((alert) => alert.status === 'cancelled').length
  const expiredCount = alerts.filter((alert) => alert.status === 'expired').length
  const activeIds = alerts
    .filter((alert) => alert.status === 'active')
    .map((alert) => alert.id)

  const summaryParts: string[] = []
  if (cancelledCount > 0) summaryParts.push(`${cancelledCount} cancelled`)
  if (expiredCount > 0) summaryParts.push(`${expiredCount} expired`)

  return (
    <div className="rounded-lg border border-border/40 bg-muted/10">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-muted/20 transition-colors"
      >
        <div className="flex items-center gap-2">
          <ChevronDown
            className={cn(
              'h-4 w-4 text-muted-foreground transition-transform',
              !expanded && '-rotate-90',
            )}
          />
          <span className="text-sm text-muted-foreground">
            History — {summaryParts.join(' · ')}
          </span>
        </div>

        {activeIds.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-muted-foreground hover:text-destructive"
            onClick={(event) => {
              event.stopPropagation()
              onBulkCancel(activeIds)
            }}
            disabled={isBulkCancelling}
          >
            <Trash2 className="h-3 w-3 mr-1" />
            Cancel all active
          </Button>
        )}
      </button>

      {expanded && (
        <div className="border-t border-border/30">
          {dateGroups.map((group) => (
            <div key={group.label}>
              <div className="px-4 py-1.5 bg-muted/20">
                <span className="text-[10px] font-medium text-muted-foreground/70 tracking-wider">
                  {group.label}
                </span>
              </div>
              {/* Rows with alternating shade */}
              {group.alerts.map((alert, index) => (
                <HistoryRow key={alert.id} alert={alert} isEven={index % 2 === 0} />
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function HistoryRow({ alert, isEven }: { alert: Alert; isEven: boolean }) {
  const statusDot = alert.status === 'expired'
    ? 'bg-amber-500/40'
    : 'bg-muted-foreground/20'

  return (
    <div
      className={cn(
        'flex items-center gap-3 px-4 py-2 text-sm opacity-60 hover:opacity-80 transition-opacity',
        isEven ? 'bg-muted/5' : '',
      )}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full shrink-0', statusDot)} />
      <span className="font-mono font-medium text-xs w-12 shrink-0">
        {alert.ticker}
      </span>
      {alert.recommended_action && (
        <span
          className={cn(
            'text-[11px] font-mono font-medium w-10 shrink-0',
            ACTION_COLOR[alert.recommended_action] || 'text-muted-foreground',
          )}
        >
          {alert.recommended_action}
        </span>
      )}
      <div className="flex-1 min-w-0">
        {alert.conditions[0] && (
          <ConditionChip cond={alert.conditions[0]} />
        )}
      </div>
      <span className="text-[10px] text-muted-foreground shrink-0 capitalize">
        {toTitleCase(alert.status)}
      </span>
      <span className="text-[10px] text-muted-foreground shrink-0 w-20 text-right font-mono">
        {formatRelativeTime(alert.created_at)}
      </span>
    </div>
  )
}
