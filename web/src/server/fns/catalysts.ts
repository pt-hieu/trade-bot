import { createServerFn } from '@tanstack/react-start'
import { getSql } from '../db'
import type { CatalystInput } from '../../types'

export const getCatalysts = createServerFn({ method: 'GET' }).handler(async () => {
  const sql = getSql()
  const rows = await sql`
    SELECT * FROM catalysts
    WHERE pipeline_version = 'v2'
    ORDER BY status ASC, created_at DESC
  `
  return rows
})

export const createCatalyst = createServerFn({ method: 'POST' })
  .inputValidator((data: CatalystInput) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const rows = await sql`
      INSERT INTO catalysts (
        catalyst_key, event, expected, affected_tickers,
        impact, confidence, notes, source, status,
        outcome, actual_date, expected_date, last_confirmed_at
      ) VALUES (
        ${data.catalyst_key},
        ${data.event},
        ${data.expected},
        ${data.affected_tickers},
        ${data.impact},
        ${data.confidence},
        ${data.notes ?? null},
        ${data.source ?? null},
        ${data.status ?? 'active'},
        ${data.outcome ?? null},
        ${data.actual_date ?? null},
        ${data.expected_date ?? null},
        ${data.last_confirmed_at ?? null}
      )
      RETURNING *
    `
    return rows[0]
  })

type UpdateCatalystInput = { id: string } & Partial<CatalystInput>

export const updateCatalyst = createServerFn({ method: 'POST' })
  .inputValidator((data: UpdateCatalystInput) => data)
  .handler(async ({ data }) => {
    const { id, ...input } = data
    const sql = getSql()
    const rows = await sql`
      UPDATE catalysts SET
        catalyst_key = COALESCE(${input.catalyst_key ?? null}, catalyst_key),
        event = COALESCE(${input.event ?? null}, event),
        expected = COALESCE(${input.expected ?? null}, expected),
        affected_tickers = COALESCE(${input.affected_tickers ?? null}, affected_tickers),
        impact = COALESCE(${input.impact ?? null}, impact),
        confidence = COALESCE(${input.confidence ?? null}, confidence),
        notes = ${input.notes ?? null},
        source = ${input.source ?? null},
        status = COALESCE(${input.status ?? null}, status),
        outcome = ${input.outcome ?? null},
        actual_date = ${input.actual_date ?? null},
        expected_date = ${input.expected_date ?? null},
        last_confirmed_at = ${input.last_confirmed_at ?? null},
        updated_at = NOW(),
        last_updated = CURRENT_DATE
      WHERE id = ${id}
      RETURNING *
    `
    if (rows.length === 0) {
      throw new Error('Catalyst not found')
    }
    return rows[0]
  })

export const deleteCatalyst = createServerFn({ method: 'POST' })
  .inputValidator((data: { id: string }) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const rows = await sql`
      DELETE FROM catalysts WHERE id = ${data.id} RETURNING id
    `
    if (rows.length === 0) {
      throw new Error('Catalyst not found')
    }
    return { deleted: true }
  })
