import { AlertTriangle, Bell, OctagonAlert, Shield, XCircle } from 'lucide-react'
import { Button } from '../ui/button'
import { cn } from '../../lib/utils'
import type { Alert } from '../../types/index'

interface StatusCounts {
  active: number
  triggered: number
  expired: number
  cancelled: number
  total: number
}

type UrgencyTier = 'calm' | 'info' | 'warning' | 'alarm'

function countByStatus(alerts: Alert[]): StatusCounts {
  const counts: StatusCounts = { active: 0, triggered: 0, expired: 0, cancelled: 0, total: alerts.length }
  for (const alert of alerts) {
    if (alert.status in counts) {
      counts[alert.status as keyof Omit<StatusCounts, 'total'>]++
    }
  }
  return counts
}

function getUrgencyTier(triggeredCount: number): UrgencyTier {
  if (triggeredCount === 0) return 'calm'
  if (triggeredCount <= 5) return 'info'
  if (triggeredCount <= 15) return 'warning'
  return 'alarm'
}

/** Find tickers that appear 3+ times in triggered alerts */
function findStaleRepeaters(alerts: Alert[]): string[] {
  const triggered = alerts.filter((alert) => alert.status === 'triggered')
  const frequency = new Map<string, number>()
  for (const alert of triggered) {
    frequency.set(alert.ticker, (frequency.get(alert.ticker) || 0) + 1)
  }
  return Array.from(frequency.entries())
    .filter(([, count]) => count >= 3)
    .sort((entryA, entryB) => entryB[1] - entryA[1])
    .map(([ticker]) => ticker)
}

const TIER_STYLES: Record<UrgencyTier, { border: string; background: string }> = {
  calm: { border: 'border-border', background: 'bg-muted/30' },
  info: { border: 'border-amber-500/20', background: 'bg-amber-500/5' },
  warning: { border: 'border-amber-500/30', background: 'bg-amber-500/10' },
  alarm: { border: 'border-red-500/30', background: 'bg-red-500/10' },
}

const TIER_ICON = {
  calm: Shield,
  info: Bell,
  warning: AlertTriangle,
  alarm: OctagonAlert,
}

const TIER_ICON_CLASS = {
  calm: 'text-emerald-500',
  info: 'text-amber-400',
  warning: 'text-amber-500',
  alarm: 'text-red-500',
}

interface AlertStatusStripProps {
  alerts: Alert[]
  onBulkCancelTriggered?: () => void
}

export function AlertStatusStrip({ alerts, onBulkCancelTriggered }: AlertStatusStripProps) {
  const counts = countByStatus(alerts)
  const tier = getUrgencyTier(counts.triggered)
  const staleRepeaters = findStaleRepeaters(alerts)
  const styles = TIER_STYLES[tier]
  const Icon = TIER_ICON[tier]

  if (counts.total === 0) return null

  return (
    <div className={cn('rounded-lg border px-5 py-4 space-y-3', styles.border, styles.background)}>
      {/* Primary row: icon + message + chips */}
      <div className="flex items-center gap-4">
        <Icon className={cn('h-5 w-5 shrink-0', TIER_ICON_CLASS[tier])} />

        <div className="flex-1 min-w-0">
          <span className="font-medium text-sm">
            {tier === 'calm' && 'All clear — no active alerts'}
            {tier === 'info' && `${counts.triggered} alert${counts.triggered > 1 ? 's' : ''} triggered`}
            {tier === 'warning' && `${counts.triggered} alerts triggered — review needed`}
            {tier === 'alarm' && `${counts.triggered} unacted alerts — action required`}
          </span>
        </div>

        {/* Status chips */}
        <div className="flex items-center gap-3 shrink-0">
          {counts.triggered > 0 && (
            <StatusChip
              count={counts.triggered}
              label="Triggered"
              dotClassName={tier === 'alarm' ? 'bg-red-500 animate-pulse' : 'bg-amber-500 animate-pulse'}
            />
          )}
          {counts.active > 0 && (
            <StatusChip count={counts.active} label="Active" dotClassName="bg-blue-500" />
          )}
          {counts.expired > 0 && (
            <StatusChip count={counts.expired} label="Expired" dotClassName="bg-muted-foreground/40" />
          )}
          {counts.cancelled > 0 && (
            <StatusChip count={counts.cancelled} label="Cancelled" dotClassName="bg-muted-foreground/20" />
          )}
        </div>
      </div>

      {/* Escalation row: stale repeaters + bulk action (warning/alarm only) */}
      {(tier === 'warning' || tier === 'alarm') && (
        <div className="flex items-center gap-3 pl-9">
          {staleRepeaters.length > 0 && (
            <span className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground/80">
                {staleRepeaters.slice(0, 5).join(', ')}
              </span>
              {' '}triggered repeatedly with no action
            </span>
          )}
          {onBulkCancelTriggered && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 text-xs text-muted-foreground hover:text-destructive ml-auto"
              onClick={onBulkCancelTriggered}
            >
              <XCircle className="h-3 w-3 mr-1" />
              Cancel all triggered
            </Button>
          )}
        </div>
      )}
    </div>
  )
}

function StatusChip({
  count,
  label,
  dotClassName,
}: {
  count: number
  label: string
  dotClassName: string
}) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      <span className={cn('h-2 w-2 rounded-full shrink-0', dotClassName)} />
      <span className="font-medium tabular-nums">{count}</span>
      <span>{label}</span>
    </span>
  )
}
