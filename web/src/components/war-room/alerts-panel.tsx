import { Card } from '../ui/card'
import { Skeleton } from '../ui/skeleton'
import { PanelHeader, PanelError } from './panel'
import { formatRelativeTime } from '../../lib/date'
import { useAlerts } from '../../hooks/use-alerts'
import {
  ConditionChip,
  TickerCell,
  DipBuyBadge,
  PRIORITY_DOT,
  ACTION_COLOR,
} from '../alerts/components'
import type { Alert } from '../../types/index'

const PRIORITY_ORDER: Record<Alert['priority'], number> = { high: 0, normal: 1, low: 2 }

function sortAlerts(alerts: Alert[]): Alert[] {
  return [...alerts].sort((a, b) => {
    const pd = PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority]
    if (pd !== 0) return pd
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })
}

interface AlertsPanelProps {
  onTickerClick?: (ticker: string) => void
}

export function AlertsPanel({ onTickerClick }: AlertsPanelProps) {
  const { data: alerts, isLoading, error, refetch } = useAlerts('active')

  return (
    <Card className="border-border/50 py-0 gap-0 overflow-hidden">
      <PanelHeader title="Active alerts" href="/alerts" linkText="View all →" count={alerts?.length} />

      <div className="divide-y divide-border/20">
        {isLoading &&
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 px-4 py-2.5">
              <Skeleton className="h-1.5 w-1.5 rounded-full shrink-0" />
              <Skeleton className="h-4 w-12" />
              <Skeleton className="h-4 w-14" />
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-12 ml-auto" />
            </div>
          ))}

        {error && <PanelError message="Could not load alerts" onRetry={refetch} />}

        {!isLoading && !error && (!alerts || alerts.length === 0) && (
          <p className="px-4 py-4 text-xs text-muted-foreground text-center">
            No active alerts — morning brief generates alerts at 7 AM
          </p>
        )}

        {!isLoading &&
          alerts &&
          sortAlerts(alerts as any)
            .slice(0, 8)
            .map((alert) => (
              <div
                key={alert.id}
                className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/20 transition-colors cursor-pointer"
                onClick={() => onTickerClick?.(alert.ticker)}
                data-test-id={`war-room-alert-${alert.id}`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full shrink-0 ${PRIORITY_DOT[alert.priority]}`}
                />
                <span className="shrink-0" data-test-id={`alert-ticker-${alert.ticker}`}>
                  <TickerCell ticker={alert.ticker} action={alert.recommended_action} />
                </span>
                {alert.recommended_action && (
                  <span
                    className={`text-xs font-mono font-semibold shrink-0 ${ACTION_COLOR[alert.recommended_action] ?? 'text-muted-foreground'}`}
                  >
                    {alert.recommended_action}
                  </span>
                )}
                <div className="flex items-center gap-1 flex-1 min-w-0 overflow-hidden">
                  {alert.conditions[0] && (
                    <ConditionChip cond={alert.conditions[0]} />
                  )}
                  <DipBuyBadge alert={alert} />
                </div>
                <span className="text-[10px] text-muted-foreground shrink-0 font-mono">
                  {formatRelativeTime(alert.created_at)}
                </span>
              </div>
            ))}
      </div>
    </Card>
  )
}
