import { useMemo } from 'react'
import { cn, toTitleCase } from '../../lib/utils'
import { toDateStr, formatShortDate } from '../../lib/date'
import { AlertCard } from './alert-card'
import { sortByPriority } from './components'
import type { Alert } from '../../types/index'

interface AlertSourceGroupProps {
  alerts: Alert[]
  tickerFrequency?: Map<string, number>
  onEdit: (alert: Alert) => void
  onCancel: (alert: Alert) => void
  isCancelling: boolean
}

interface SourceGroup {
  key: string
  label: string
  alerts: Alert[]
}


function formatSourceDate(rawDate: unknown): string {
  if (!rawDate) return ''
  try {
    const normalized = toDateStr(rawDate)
    if (!normalized || normalized === 'Invalid Date') return ''
    return formatShortDate(normalized)
  } catch {
    return ''
  }
}

function groupBySource(alerts: Alert[]): SourceGroup[] {
  const sorted = sortByPriority(alerts)
  const groups = new Map<string, Alert[]>()

  for (const alert of sorted) {
    const dateKey = toDateStr(alert.source_date)
    const sourceKey = `${alert.source}::${dateKey}`
    const existing = groups.get(sourceKey) || []
    existing.push(alert)
    groups.set(sourceKey, existing)
  }

  return Array.from(groups.entries()).map(([key, groupAlerts]) => {
    const [source, sourceDate] = key.split('::')
    const sourceLabel = toTitleCase(source)
    const dateLabel = formatSourceDate(sourceDate)
    return {
      key,
      label: dateLabel ? `${sourceLabel} — ${dateLabel}` : sourceLabel,
      alerts: groupAlerts,
    }
  })
}

function AlertGrid({
  alerts,
  tickerFrequency,
  onEdit,
  onCancel,
  isCancelling,
}: AlertSourceGroupProps) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {alerts.map((alert) => (
        <div
          key={alert.id}
          className={cn(alert.priority === 'high' && 'md:col-span-2')}
        >
          <AlertCard
            alert={alert}
            repeatCount={tickerFrequency?.get(alert.ticker) || 0}
            onEdit={onEdit}
            onCancel={onCancel}
            isCancelling={isCancelling}
          />
        </div>
      ))}
    </div>
  )
}

export function AlertSourceGroup({
  alerts,
  tickerFrequency,
  onEdit,
  onCancel,
  isCancelling,
}: AlertSourceGroupProps) {
  const groups = useMemo(() => groupBySource(alerts), [alerts])

  if (groups.length === 1) {
    return (
      <AlertGrid
        alerts={groups[0].alerts}
        tickerFrequency={tickerFrequency}
        onEdit={onEdit}
        onCancel={onCancel}
        isCancelling={isCancelling}
      />
    )
  }

  return (
    <div className="space-y-4">
      {groups.map((group) => (
        <div key={group.key} className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">
              {group.label}
            </span>
            <span className="text-[10px] text-muted-foreground/50 tabular-nums">
              {group.alerts.length} alert{group.alerts.length > 1 ? 's' : ''}
            </span>
            <div className="flex-1 border-t border-border/20" />
          </div>
          <AlertGrid
            alerts={group.alerts}
            tickerFrequency={tickerFrequency}
            onEdit={onEdit}
            onCancel={onCancel}
            isCancelling={isCancelling}
          />
        </div>
      ))}
    </div>
  )
}
