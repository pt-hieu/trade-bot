import { createServerFn } from '@tanstack/react-start'
import { getSql } from '../db'
import type { CapitalEventInput } from '../../types'

export const getCapitalEvents = createServerFn({ method: 'GET' }).handler(async () => {
  const sql = getSql()
  const rows = await sql`
    SELECT * FROM capital_events
    ORDER BY status ASC, created_at DESC
  `
  return rows
})

export const createCapitalEvent = createServerFn({ method: 'POST' })
  .inputValidator((data: CapitalEventInput) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const rows = await sql`
      INSERT INTO capital_events (
        event_key, ticker, event_type, description,
        amount, expected_date, dilution_pct,
        impact, source, status
      ) VALUES (
        ${data.event_key},
        ${data.ticker.toUpperCase()},
        ${data.event_type},
        ${data.description},
        ${data.amount ?? null},
        ${data.expected_date},
        ${data.dilution_pct ?? null},
        ${data.impact},
        ${data.source ?? null},
        ${data.status ?? 'pending'}
      )
      RETURNING *
    `
    return rows[0]
  })

type UpdateCapitalEventInput = { id: string } & Partial<CapitalEventInput>

export const updateCapitalEvent = createServerFn({ method: 'POST' })
  .inputValidator((data: UpdateCapitalEventInput) => data)
  .handler(async ({ data }) => {
    const { id, ...input } = data
    const sql = getSql()
    const rows = await sql`
      UPDATE capital_events SET
        event_key = COALESCE(${input.event_key ?? null}, event_key),
        ticker = COALESCE(${input.ticker ? input.ticker.toUpperCase() : null}, ticker),
        event_type = COALESCE(${input.event_type ?? null}, event_type),
        description = COALESCE(${input.description ?? null}, description),
        amount = ${input.amount ?? null},
        expected_date = COALESCE(${input.expected_date ?? null}, expected_date),
        dilution_pct = ${input.dilution_pct ?? null},
        impact = COALESCE(${input.impact ?? null}, impact),
        source = ${input.source ?? null},
        status = COALESCE(${input.status ?? null}, status),
        updated_at = NOW()
      WHERE id = ${id}
      RETURNING *
    `
    if (rows.length === 0) {
      throw new Error('Capital event not found')
    }
    return rows[0]
  })

export const deleteCapitalEvent = createServerFn({ method: 'POST' })
  .inputValidator((data: { id: string }) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const rows = await sql`
      DELETE FROM capital_events WHERE id = ${data.id} RETURNING id
    `
    if (rows.length === 0) {
      throw new Error('Capital event not found')
    }
    return { deleted: true }
  })
