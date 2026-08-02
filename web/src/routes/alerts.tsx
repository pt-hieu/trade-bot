import { createFileRoute } from '@tanstack/react-router'
import { useState, useMemo } from 'react'
import { Bell, Clock, Plus, Search, X } from 'lucide-react'
import { Button } from '../components/ui/button'
import { Skeleton } from '../components/ui/skeleton'
import { EmptyState } from '../components/ui/empty-state'
import { ErrorState } from '../components/ui/error-state'
import { ConfirmDialog } from '../components/ui/confirm-dialog'
import { AlertDialog } from '../components/alert-dialog'
import { AlertStatusStrip } from '../components/alerts/alert-status-strip'
import { AlertHistorySection } from '../components/alerts/alert-history-section'
import { AlertSourceGroup } from '../components/alerts/alert-source-group'
import { AlertTickerStack } from '../components/alerts/alert-ticker-stack'
import { useAlerts, useCancelAlert, useBulkCancelAlerts } from '../hooks/use-alerts'
import { CONDITION_CONFIG } from '../components/alerts/components'
import type { Alert } from '../types/index'

export const Route = createFileRoute('/alerts')({
  component: AlertsPage,
  ssr: false,
})

const TWENTY_FOUR_HOURS_MS = 24 * 60 * 60 * 1000

function AlertsPage() {
  const { data: alertsRaw, isLoading, error, refetch } = useAlerts()
  const alerts = (alertsRaw ?? []) as Alert[]
  const cancelAlert = useCancelAlert()
  const bulkCancel = useBulkCancelAlerts()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [selectedAlert, setSelectedAlert] = useState<Alert | undefined>()
  const [cancelTarget, setCancelTarget] = useState<Alert | undefined>()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [bulkCancelConfirmOpen, setBulkCancelConfirmOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  // ── Partition alerts by status + freshness ─────────────────────
  const { freshTriggered, agingTriggered, activeAlerts, historyAlerts, bulkCancelDescription } =
    useMemo(() => {
      let filtered = alerts
      if (searchQuery) {
        const query = searchQuery.toLowerCase()
        filtered = alerts.filter(
          (alert) =>
            alert.ticker.toLowerCase().includes(query) ||
            alert.rationale?.toLowerCase().includes(query) ||
            alert.recommended_action?.toLowerCase().includes(query),
        )
      }

      // Single-pass partition
      const freshTriggered: Alert[] = []
      const agingTriggered: Alert[] = []
      const activeAlerts: Alert[] = []
      const historyAlerts: Alert[] = []
      const now = Date.now()
      const priorityCounts = { high: 0, normal: 0, low: 0 }
      const tickerSet = new Set<string>()

      for (const alert of filtered) {
        if (alert.status === 'triggered') {
          const triggeredTime = alert.triggered_at
            ? new Date(alert.triggered_at).getTime()
            : new Date(alert.created_at).getTime()
          if (now - triggeredTime < TWENTY_FOUR_HOURS_MS) {
            freshTriggered.push(alert)
          } else {
            agingTriggered.push(alert)
          }
          priorityCounts[alert.priority]++
          tickerSet.add(alert.ticker)
        } else if (alert.status === 'active') {
          activeAlerts.push(alert)
        } else {
          historyAlerts.push(alert)
        }
      }

      const triggeredTotal = freshTriggered.length + agingTriggered.length
      const priorityParts: string[] = []
      if (priorityCounts.high > 0) priorityParts.push(`${priorityCounts.high} HIGH`)
      if (priorityCounts.normal > 0) priorityParts.push(`${priorityCounts.normal} normal`)
      if (priorityCounts.low > 0) priorityParts.push(`${priorityCounts.low} low`)

      return {
        freshTriggered,
        agingTriggered,
        activeAlerts,
        historyAlerts,
        bulkCancelDescription: triggeredTotal > 0
          ? `Cancel ${triggeredTotal} triggered alerts? ${priorityParts.join(', ')} priority. Tickers: ${[...tickerSet].join(', ')}. This cannot be undone.`
          : '',
      }
    }, [alerts, searchQuery])

  const handleNewAlert = () => {
    setSelectedAlert(undefined)
    setDialogOpen(true)
  }

  const handleEdit = (alert: Alert) => {
    setSelectedAlert(alert)
    setDialogOpen(true)
  }

  const handleCancelRequest = (alert: Alert) => {
    setCancelTarget(alert)
    setConfirmOpen(true)
  }

  const getCancelDescription = (alert?: Alert) => {
    if (!alert) return ''
    const condition = alert.conditions?.[0]
    const conditionLabel = condition
      ? CONDITION_CONFIG[condition.condition_type]?.label ?? condition.condition_type
      : ''
    const extra =
      alert.conditions?.length > 1 ? ` (+${alert.conditions.length - 1} more)` : ''
    return `Cancel the ${conditionLabel}${extra} alert for ${alert.ticker}? This will stop monitoring.`
  }

  return (
    <main className="min-h-[calc(100dvh-77px)] p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Alerts</h1>
        <div className="flex items-center gap-3">
          {alerts.length > 0 && (
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search..."
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                className="h-8 w-48 rounded-md border border-border bg-background pl-8 pr-7 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 cursor-pointer"
                >
                  <X className="h-3 w-3 text-muted-foreground" />
                </button>
              )}
            </div>
          )}
          <Button onClick={handleNewAlert} size="sm">
            <Plus className="h-4 w-4 mr-1" />
            New Alert
          </Button>
        </div>
      </div>

      {isLoading && <AlertsLoadingSkeleton />}
      {error && <ErrorState description="Could not load alerts." retry={refetch} />}
      {!isLoading && !error && alerts.length === 0 && (
        <EmptyState
          icon={Bell}
          title="No alerts monitoring"
          description="Morning brief generates alerts automatically at 7 AM on trading days. Create a manual alert to monitor specific levels."
          action={{ label: '+ New Alert', onClick: handleNewAlert }}
        />
      )}

      {!isLoading && !error && alerts.length > 0 && (
        <>
          <AlertStatusStrip
            alerts={alerts}
            onBulkCancelTriggered={() => setBulkCancelConfirmOpen(true)}
          />

          {/* Fresh triggered — ticker stacks */}
          {freshTriggered.length > 0 && (
            <AlertSection title="Just Triggered" count={freshTriggered.length}>
              <AlertTickerStack
                alerts={freshTriggered}
                onCancel={handleCancelRequest}
                isCancelling={cancelAlert.isPending}
              />
            </AlertSection>
          )}

          {/* Aging triggered — ticker stacks, muted */}
          {agingTriggered.length > 0 && (
            <AlertSection
              title="Aging — Not Acted On"
              count={agingTriggered.length}
              icon={Clock}
              muted
            >
              <AlertTickerStack
                alerts={agingTriggered}
                onCancel={handleCancelRequest}
                isCancelling={cancelAlert.isPending}
              />
            </AlertSection>
          )}

          {/* Active — source-grouped cards */}
          {activeAlerts.length > 0 && (
            <AlertSection title="Monitoring" count={activeAlerts.length}>
              <AlertSourceGroup
                alerts={activeAlerts}
                onEdit={handleEdit}
                onCancel={handleCancelRequest}
                isCancelling={cancelAlert.isPending}
              />
            </AlertSection>
          )}

          <AlertHistorySection
            alerts={historyAlerts}
            onBulkCancel={(ids) => bulkCancel.mutate(ids)}
            isBulkCancelling={bulkCancel.isPending}
          />
        </>
      )}

      {/* Single alert cancel */}
      <AlertDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        alert={selectedAlert}
      />

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Cancel Alert"
        description={getCancelDescription(cancelTarget)}
        confirmText="Cancel Alert"
        variant="destructive"
        onConfirm={async () => {
          if (!cancelTarget) return
          await cancelAlert.mutateAsync(cancelTarget.id)
          setConfirmOpen(false)
          setCancelTarget(undefined)
        }}
        isPending={cancelAlert.isPending}
      />

      {/* Bulk dismiss confirmation */}
      <ConfirmDialog
        open={bulkCancelConfirmOpen}
        onOpenChange={setBulkCancelConfirmOpen}
        title="Cancel All Triggered Alerts"
        description={bulkCancelDescription}
        confirmText="Cancel All"
        variant="destructive"
        onConfirm={async () => {
          const triggeredIds = alerts
            .filter((alert) => alert.status === 'triggered')
            .map((alert) => alert.id)
          if (triggeredIds.length > 0) {
            await bulkCancel.mutateAsync(triggeredIds)
          }
          setBulkCancelConfirmOpen(false)
        }}
        isPending={bulkCancel.isPending}
      />
    </main>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────

function AlertSection({
  title,
  count,
  icon: Icon,
  muted,
  children,
}: {
  title: string
  count: number
  icon?: typeof Clock
  muted?: boolean
  children: React.ReactNode
}) {
  return (
    <section className={muted ? 'space-y-3 opacity-75' : 'space-y-3'}>
      <div className="flex items-center gap-2">
        {Icon && <Icon className="h-3.5 w-3.5 text-amber-500" />}
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        <span className="text-xs text-muted-foreground tabular-nums">({count})</span>
      </div>
      {children}
    </section>
  )
}

function AlertsLoadingSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-14 w-full rounded-lg" />
      <div className="space-y-2">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-14 rounded-lg" />
        <Skeleton className="h-14 rounded-lg" />
        <Skeleton className="h-14 rounded-lg" />
      </div>
      <Skeleton className="h-12 w-full rounded-lg" />
    </div>
  )
}
