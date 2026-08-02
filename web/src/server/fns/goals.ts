import { createServerFn } from '@tanstack/react-start'
import { getSql, buildSetClause } from '../db'
import { syncGoalProgress } from '../goal-sync'

// ─── Types ────────────────────────────────────────────────────────────────────

interface GoalInput {
  name: string
  target_vnd: number
  realized_vnd?: number
  start_date: string
  deadline: string
  status: 'Active' | 'Achieved' | 'Failed' | 'Paused' | 'Tracking'
  goal_type: 'Monthly' | 'Quarterly' | 'Yearly' | 'Custom'
  notes?: string | null
}

interface GoalUpdateParams {
  id: string
  input: Partial<GoalInput>
}

interface GoalDeleteParams {
  id: string
}

// ─── GET /goals ────────────────────────────────────────────────────────────────

export const getGoals = createServerFn({ method: 'GET' }).handler(async () => {
  const sql = getSql()
  const rows = await sql`
    SELECT
      id,
      name,
      target_vnd,
      realized_vnd,
      start_date,
      deadline,
      status,
      goal_type,
      notes
    FROM goals
    ORDER BY deadline DESC
  `
  return rows
})

// ─── POST /goals ───────────────────────────────────────────────────────────────

export const createGoal = createServerFn({ method: 'POST' })
  .inputValidator((data: GoalInput) => data)
  .handler(async ({ data: input }) => {
    const sql = getSql()

    const rows = await sql`
      INSERT INTO goals (
        name,
        target_vnd,
        realized_vnd,
        start_date,
        deadline,
        status,
        goal_type,
        notes
      ) VALUES (
        ${input.name},
        ${input.target_vnd},
        ${input.realized_vnd ?? 0},
        ${input.start_date},
        ${input.deadline},
        ${input.status},
        ${input.goal_type},
        ${input.notes ?? null}
      )
      RETURNING *
    `

    await syncGoalProgress()

    const synced = await sql`SELECT * FROM goals WHERE id = ${rows[0].id}`
    return synced[0]
  })

// ─── PUT /goals/:id ────────────────────────────────────────────────────────────

export const updateGoal = createServerFn({ method: 'POST' })
  .inputValidator((data: GoalUpdateParams) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const { id, input } = data

    const updates: Record<string, unknown> = {}

    if (input.name !== undefined) updates.name = input.name
    if (input.target_vnd !== undefined) updates.target_vnd = input.target_vnd
    if (input.realized_vnd !== undefined) updates.realized_vnd = input.realized_vnd
    if (input.start_date !== undefined) updates.start_date = input.start_date
    if (input.deadline !== undefined) updates.deadline = input.deadline
    if (input.status !== undefined) updates.status = input.status
    if (input.goal_type !== undefined) updates.goal_type = input.goal_type
    if (input.notes !== undefined) updates.notes = input.notes

    if (Object.keys(updates).length === 0) {
      throw new Error('No fields to update')
    }

    const { clause, values } = buildSetClause(updates)
    const rows = await sql(
      `UPDATE goals SET ${clause} WHERE id = $1 RETURNING *`,
      [id, ...values]
    )

    if (rows.length === 0) {
      throw new Error('Goal not found')
    }

    await syncGoalProgress()

    const synced = await sql`SELECT * FROM goals WHERE id = ${id}`
    return synced[0]
  })

// ─── DELETE /goals/:id ─────────────────────────────────────────────────────────

export const deleteGoal = createServerFn({ method: 'POST' })
  .inputValidator((data: GoalDeleteParams) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const { id } = data

    const rows = await sql`
      DELETE FROM goals
      WHERE id = ${id}
      RETURNING id
    `

    if (rows.length === 0) {
      throw new Error('Goal not found')
    }

    return { success: true }
  })
