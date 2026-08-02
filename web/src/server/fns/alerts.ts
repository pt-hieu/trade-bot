import { createServerFn } from '@tanstack/react-start'
import { getSql, buildSetClause } from '../db'
import { ALERTS_BASE_QUERY, parseAlertRows } from '../queries/alerts'

// ─── Types ────────────────────────────────────────────────────────────────────

type AlertConditionType = 'price_below' | 'price_above' | 'rsi_below' | 'rsi_above' | 'volume_spike'
type AlertAction = 'BUY' | 'TRIM' | 'EXIT' | 'ADD' | 'WATCH'

interface AlertConditionInput {
  type: AlertConditionType
  value: number
}

interface AlertInput {
  ticker: string
  conditions: AlertConditionInput[]
  condition_logic?: 'ALL' | 'ANY'
  recommended_action: AlertAction | null
  priority: 'high' | 'normal' | 'low'
  rationale?: string | null
  entry_price?: number | null
  stop_price?: number | null
  target_price?: number | null
}

interface AlertsGetParams {
  status?: string
  ticker?: string
}

interface AlertUpdateParams {
  id: string
  input: Partial<AlertInput>
}

interface AlertDeleteParams {
  id: string
}

// ─── GET /alerts/badge-count ──────────────────────────────────────────────────

export const getAlertBadgeCount = createServerFn({ method: 'GET' })
  .handler(async () => {
    const sql = getSql()
    const rows = await sql`
      SELECT COUNT(*)::int AS count
      FROM alerts
      WHERE status = 'triggered'
    `
    return (rows[0]?.count as number) || 0
  })

// ─── GET /alerts ───────────────────────────────────────────────────────────────

export const getAlerts = createServerFn({ method: 'GET' })
  .inputValidator((data: AlertsGetParams) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const { status, ticker } = data

    // Sort active/triggered first so they're never cut off by the LIMIT
    const ORDER_CLAUSE = `ORDER BY CASE WHEN a.status IN ('triggered', 'active') THEN 0 ELSE 1 END, a.created_at DESC LIMIT 200`

    let rows: Record<string, unknown>[]
    if (status && ticker) {
      rows = await sql(
        `${ALERTS_BASE_QUERY} WHERE a.status = $1 AND a.ticker = $2 GROUP BY a.id ${ORDER_CLAUSE}`,
        [status, ticker.toUpperCase()]
      )
    } else if (status) {
      rows = await sql(
        `${ALERTS_BASE_QUERY} WHERE a.status = $1 GROUP BY a.id ${ORDER_CLAUSE}`,
        [status]
      )
    } else if (ticker) {
      rows = await sql(
        `${ALERTS_BASE_QUERY} WHERE a.ticker = $1 GROUP BY a.id ${ORDER_CLAUSE}`,
        [ticker.toUpperCase()]
      )
    } else {
      rows = await sql(
        `${ALERTS_BASE_QUERY} GROUP BY a.id ${ORDER_CLAUSE}`,
        []
      )
    }

    return parseAlertRows(rows)
  })

// ─── POST /alerts ──────────────────────────────────────────────────────────────

export const createAlert = createServerFn({ method: 'POST' })
  .inputValidator((data: AlertInput) => data)
  .handler(async ({ data: input }) => {
    const sql = getSql()
    const today = new Date().toISOString().split('T')[0]
    const conditions = input.conditions ?? []
    const conditionLogic = input.condition_logic ?? 'ALL'

    if (conditions.length === 0) {
      throw new Error('At least one condition required')
    }
    if (conditions.length > 5) {
      throw new Error('Max 5 conditions')
    }

    const alertRows = await sql`
      INSERT INTO alerts (
        ticker, condition_logic,
        recommended_action, priority, rationale,
        entry_price, stop_price, target_price,
        source, source_date, action_type, status
      ) VALUES (
        ${input.ticker.toUpperCase()},
        ${conditionLogic},
        ${input.recommended_action ?? null},
        ${input.priority},
        ${input.rationale ?? null},
        ${input.entry_price ?? null},
        ${input.stop_price ?? null},
        ${input.target_price ?? null},
        'manual',
        ${today},
        'notify',
        'active'
      )
      RETURNING id
    `
    const alertId = alertRows[0].id as number

    // Batch insert all conditions in a single statement
    const params: unknown[] = []
    const valueClauses = conditions.map((condition, index) => {
      const base = params.length + 1
      params.push(alertId, condition.type, condition.value, index)
      return `($${base}, $${base + 1}, $${base + 2}, $${base + 3})`
    })
    await sql(
      `INSERT INTO alert_conditions (alert_id, condition_type, condition_value, sort_order) VALUES ${valueClauses.join(', ')}`,
      params
    )

    await sql`
      INSERT INTO alert_history (alert_id, event_type, event_data)
      VALUES (${alertId}, 'created', '{"source": "web_app"}'::jsonb)
    `

    const fullRows = await sql(
      `${ALERTS_BASE_QUERY} WHERE a.id = $1 GROUP BY a.id`,
      [alertId]
    )
    return parseAlertRows(fullRows as Record<string, unknown>[])[0]
  })

// ─── PUT /alerts/:id ───────────────────────────────────────────────────────────

export const updateAlert = createServerFn({ method: 'POST' })
  .inputValidator((data: AlertUpdateParams) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const { id, input } = data

    const existing = await sql`SELECT id, status FROM alerts WHERE id = ${id}`
    if (existing.length === 0) {
      throw new Error('Alert not found')
    }
    if (existing[0].status !== 'active') {
      throw new Error('Only active alerts can be edited')
    }

    const updates: Record<string, unknown> = {}
    if (input.condition_logic !== undefined) updates.condition_logic = input.condition_logic
    if (input.recommended_action !== undefined) updates.recommended_action = input.recommended_action
    if (input.priority !== undefined) updates.priority = input.priority
    if (input.rationale !== undefined) updates.rationale = input.rationale
    if (input.entry_price !== undefined) updates.entry_price = input.entry_price
    if (input.stop_price !== undefined) updates.stop_price = input.stop_price
    if (input.target_price !== undefined) updates.target_price = input.target_price
    updates.updated_at = new Date().toISOString()

    if (Object.keys(updates).length > 1) {
      const { clause, values } = buildSetClause(updates)
      await sql(`UPDATE alerts SET ${clause} WHERE id = $1`, [id, ...values])
    }

    if (input.conditions !== undefined) {
      if (input.conditions.length === 0) {
        throw new Error('At least one condition required')
      }
      if (input.conditions.length > 5) {
        throw new Error('Max 5 conditions')
      }

      await sql`DELETE FROM alert_conditions WHERE alert_id = ${id}`

      for (let conditionIndex = 0; conditionIndex < input.conditions.length; conditionIndex++) {
        const condition = input.conditions[conditionIndex]
        await sql`
          INSERT INTO alert_conditions (alert_id, condition_type, condition_value, sort_order)
          VALUES (${id}, ${condition.type}, ${condition.value}, ${conditionIndex})
        `
      }
    }

    const rows = await sql(`${ALERTS_BASE_QUERY} WHERE a.id = $1 GROUP BY a.id`, [id])
    return parseAlertRows(rows as Record<string, unknown>[])[0]
  })

// ─── DELETE /alerts/:id ────────────────────────────────────────────────────────

export const deleteAlert = createServerFn({ method: 'POST' })
  .inputValidator((data: AlertDeleteParams) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const { id } = data

    const rows = await sql`
      UPDATE alerts
      SET status = 'cancelled', updated_at = NOW()
      WHERE id = ${id} AND status IN ('active', 'triggered')
      RETURNING id
    `

    if (rows.length === 0) {
      throw new Error('Alert not found or already cancelled')
    }

    await sql`
      INSERT INTO alert_history (alert_id, event_type, event_data)
      VALUES (${id}, 'cancelled', '{"source": "web_app"}'::jsonb)
    `

    return { success: true }
  })

// ─── BULK CANCEL ──────────────────────────────────────────────────────────────

export const bulkCancelAlerts = createServerFn({ method: 'POST' })
  .inputValidator((data: { ids: string[] }) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const { ids } = data

    if (ids.length === 0) return { cancelled: 0 }

    const rows = await sql`
      UPDATE alerts
      SET status = 'cancelled', updated_at = NOW()
      WHERE id = ANY(${ids}::bigint[]) AND status IN ('active', 'triggered')
      RETURNING id
    `

    const cancelledIds = rows.map((row) => row.id as number)
    if (cancelledIds.length > 0) {
      await sql`
        INSERT INTO alert_history (alert_id, event_type, event_data)
        SELECT unnest(${cancelledIds}::bigint[]), 'cancelled', '{"source": "web_app_bulk"}'::jsonb
      `
    }

    return { cancelled: rows.length }
  })
