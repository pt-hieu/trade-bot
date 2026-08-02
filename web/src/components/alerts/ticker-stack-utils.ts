import { toTitleCase } from '../../lib/utils'
import { toDateStr, formatShortDate } from '../../lib/date'
import { PRIORITY_ORDER } from './components'
import type { Alert, AlertConditionType } from '../../types/index'

// ── Types ────────────────────────────────────────────────────────────────

export interface ActionSubGroup {
  action: string | null
  alerts: Alert[]
  isDuplicated: boolean
  uniqueSources: string[]
  latestTriggeredPrice: number | null
  conditionStillMet: boolean | null
}

export interface TickerGroup {
  ticker: string
  highestPriority: Alert['priority']
  actionSubGroups: ActionSubGroup[]
  totalCount: number
  anyConditionLive: boolean | null
  hasMultiSource: boolean
  actionabilityScore: number
}

// ── Condition-aware price logic ──────────────────────────────────────────

const BELOW_CONDITIONS: AlertConditionType[] = ['price_below', 'rsi_below']

function isConditionStillMet(
  conditionType: AlertConditionType,
  threshold: number | null,
  currentPrice: number | null,
): boolean | null {
  if (threshold == null || currentPrice == null) return null
  if (BELOW_CONDITIONS.includes(conditionType)) {
    return currentPrice <= threshold
  }
  return currentPrice >= threshold
}

// ── Grouping helpers ─────────────────────────────────────────────────────

function areAllDuplicated(alerts: Alert[]): boolean {
  if (alerts.length <= 1) return false
  const firstCondition = alerts[0].conditions[0]
  if (!firstCondition) return false
  return alerts.every((alert) => {
    const condition = alert.conditions[0]
    return (
      condition &&
      condition.condition_type === firstCondition.condition_type &&
      condition.condition_value === firstCondition.condition_value
    )
  })
}

export function getTriggeredPrice(alert: Alert): number | null {
  if (!alert.triggered_values) return null
  const values = Object.values(alert.triggered_values)
  return values.length > 0 ? values[0] : null
}

export function compressSourceDates(alerts: Alert[]): string {
  const sourceGroups = new Map<string, Map<string, number>>()
  for (const alert of alerts) {
    const sourceName = toTitleCase(alert.source)
    const dateLabel = formatShortDate(toDateStr(alert.source_date))
    if (!sourceGroups.has(sourceName)) sourceGroups.set(sourceName, new Map())
    const dates = sourceGroups.get(sourceName)!
    dates.set(dateLabel, (dates.get(dateLabel) || 0) + 1)
  }

  return Array.from(sourceGroups.entries())
    .map(([source, dates]) => {
      const dateParts = Array.from(dates.entries()).map(([date, count]) =>
        count > 1 ? `${date} (×${count})` : date,
      )
      return `${source}: ${dateParts.join(', ')}`
    })
    .join(' · ')
}

// ── Main grouping function ───────────────────────────────────────────────

export function groupByTicker(alerts: Alert[]): TickerGroup[] {
  const tickerMap = new Map<string, Alert[]>()
  for (const alert of alerts) {
    const existing = tickerMap.get(alert.ticker) || []
    existing.push(alert)
    tickerMap.set(alert.ticker, existing)
  }

  return Array.from(tickerMap.entries())
    .map(([ticker, tickerAlerts]) => {
      const actionMap = new Map<string, Alert[]>()
      for (const alert of tickerAlerts) {
        const actionKey = alert.recommended_action || '_none'
        const existing = actionMap.get(actionKey) || []
        existing.push(alert)
        actionMap.set(actionKey, existing)
      }

      const actionSubGroups: ActionSubGroup[] = Array.from(actionMap.entries())
        .map(([actionKey, actionAlerts]) => {
          const sorted = [...actionAlerts].sort(
            (alertA, alertB) =>
              new Date(alertB.created_at).getTime() - new Date(alertA.created_at).getTime(),
          )
          const uniqueSources = [
            ...new Set(sorted.map((alert) => toTitleCase(alert.source))),
          ]
          const latestTriggeredPrice = getTriggeredPrice(sorted[0])
          const latestCondition = sorted[0].conditions[0]
          const conditionStillMet = latestCondition
            ? isConditionStillMet(
                latestCondition.condition_type,
                latestCondition.condition_value,
                latestTriggeredPrice,
              )
            : null

          return {
            action: actionKey === '_none' ? null : actionKey,
            alerts: sorted,
            isDuplicated: areAllDuplicated(sorted),
            uniqueSources,
            latestTriggeredPrice,
            conditionStillMet,
          }
        })
        .sort((groupA, groupB) => {
          const orderA = groupA.action === 'BUY' || groupA.action === 'ADD' ? 0 : 1
          const orderB = groupB.action === 'BUY' || groupB.action === 'ADD' ? 0 : 1
          return orderA - orderB
        })

      const highestPriority = tickerAlerts.reduce<Alert['priority']>(
        (best, alert) =>
          (PRIORITY_ORDER[alert.priority] ?? 1) < (PRIORITY_ORDER[best] ?? 1)
            ? alert.priority
            : best,
        'low',
      )

      const liveStates = actionSubGroups.map((subGroup) => subGroup.conditionStillMet)
      const hasAnyLive = liveStates.some((state) => state === true)
      const hasAnyDead = liveStates.some((state) => state === false)
      const anyConditionLive = hasAnyLive ? true : hasAnyDead ? false : null

      const hasMultiSource = actionSubGroups.some(
        (subGroup) => subGroup.uniqueSources.length > 1,
      )

      const livenessScore = anyConditionLive === true ? 0 : anyConditionLive === null ? 1 : 2
      const priorityScore = PRIORITY_ORDER[highestPriority] ?? 1
      const multiSourceBonus = hasMultiSource ? -0.5 : 0
      const actionabilityScore = livenessScore * 10 + priorityScore + multiSourceBonus

      return {
        ticker,
        highestPriority,
        actionSubGroups,
        totalCount: tickerAlerts.length,
        anyConditionLive,
        hasMultiSource,
        actionabilityScore,
      }
    })
    .sort((groupA, groupB) => groupA.actionabilityScore - groupB.actionabilityScore)
}
