import { getSql } from './db'

export async function syncGoalProgress(): Promise<void> {
  const sql = getSql()

  const goals = await sql`
    SELECT id, start_date, deadline
    FROM goals
    WHERE status IN ('Active', 'Tracking')
  `

  if (goals.length === 0) return

  for (const goal of goals) {
    const result = await sql`
      SELECT COALESCE(SUM(pl_net_vnd), 0) as realized
      FROM trades_calculated
      WHERE status = 'CLOSED'
        AND exit_date >= ${goal.start_date}
        AND exit_date <= ${goal.deadline}
    `

    await sql`
      UPDATE goals
      SET realized_vnd = ${result[0].realized}, updated_at = NOW()
      WHERE id = ${goal.id}
    `
  }
}
