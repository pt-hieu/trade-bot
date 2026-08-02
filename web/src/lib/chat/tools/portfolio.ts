/**
 * Portfolio domain tools — holdings, trades, cash, goals, position sizing.
 */
import { z } from 'zod'
import type { Tool } from 'ai'
import { getSql } from './shared'

// ─── Portfolio ────────────────────────────────────────────────────────────────

const get_portfolio: Tool = {
  description:
    'Get current portfolio holdings with P&L, market value, sector, and weight. Prices in thousands VND (multiply by 1000 for VND).',
  inputSchema: z.object({
    render: z.boolean().optional().describe('Set true to render a holdings table in the chat'),
  }),
  execute: async () => {
    const sql = getSql()
    const rows = await sql`
      SELECT ticker, holding_type, shares, avg_cost_vnd, current_price_vnd,
             cost_basis_vnd, market_value_vnd, pl_vnd, pl_pct, sector_name
      FROM v_portfolio_current
      ORDER BY market_value_vnd DESC
    `
    return JSON.stringify(rows)
  },
}

// ─── Trades ───────────────────────────────────────────────────────────────────

const _tradesSchema = z.object({
  all: z.boolean().optional().describe('Return full trade history (default: false, returns last 10)'),
  status: z.enum(['OPEN', 'CLOSED', 'all']).optional().describe('Filter by trade status'),
  days_back: z
    .number()
    .optional()
    .describe('Only return trades within the last N days (e.g. 1 for today, 7 for this week)'),
  ticker: z.string().optional().describe('Filter trades by ticker symbol'),
  render: z.boolean().optional().describe('Set true to render a trades table in the chat'),
})

const get_trades: Tool = {
  description:
    'Get recent trades. Default returns latest 10. Use days_back to filter by recency (e.g. days_back=1 for today). Use ticker to filter by symbol.',
  inputSchema: _tradesSchema,
  execute: async (input: z.infer<typeof _tradesSchema>) => {
    const { all, status, days_back, ticker } = input
    const sql = getSql()
    const limit = all ? 100 : 10

    // neon() HTTP driver doesn't support nested sql`` fragments,
    // so build dynamic WHERE with explicit parameterization
    const conditions: string[] = []
    const params: unknown[] = []

    if (status && status !== 'all') {
      params.push(status)
      conditions.push(`status = $${params.length}`)
    }
    if (ticker) {
      params.push(ticker.toUpperCase())
      conditions.push(`ticker = $${params.length}`)
    }
    if (days_back) {
      params.push(days_back)
      const idx = params.length
      conditions.push(`(entry_date >= CURRENT_DATE - $${idx} OR exit_date >= CURRENT_DATE - $${idx})`)
    }

    const where = conditions.length ? conditions.join(' AND ') : 'TRUE'
    params.push(limit)

    try {
      const rows = await sql(
        `SELECT id, ticker, plan_type, strategy, entry_date, entry_price_vnd,
                exit_date, exit_price_vnd, shares, buy_total_vnd, pl_net_vnd,
                ROUND(pl_pct, 2) AS pl_pct,
                exit_date - entry_date AS days_held,
                CASE WHEN status != 'CLOSED' THEN NULL
                     WHEN pl_net_vnd >= 0 THEN 'WIN' ELSE 'LOSS' END AS result,
                status
         FROM trades_calculated
         WHERE ${where}
         ORDER BY COALESCE(exit_date, entry_date) DESC
         LIMIT $${params.length}`,
        params,
      )
      return JSON.stringify(rows)
    } catch (e) {
      return JSON.stringify({ error: `get_trades failed: ${String(e)}` })
    }
  },
}

// ─── Cash ─────────────────────────────────────────────────────────────────────

const get_cash: Tool = {
  description:
    'Get current cash balance, reserve amount, and deployable capital. Also includes risk parameters (max risk per trade, max concurrent positions).',
  inputSchema: z.object({}),
  execute: async () => {
    const sql = getSql()
    const [cashRows, config] = await Promise.all([
      sql`SELECT market_value_vnd AS total_cash_vnd FROM v_portfolio_current WHERE ticker = 'CASH' LIMIT 1`,
      sql`SELECT min_cash_reserve, max_risk_per_trade, max_concurrent_positions FROM trading_config LIMIT 1`,
    ])
    const totalCash = cashRows[0]?.total_cash_vnd ? Number(cashRows[0].total_cash_vnd) : 0
    const reserve = config[0]?.min_cash_reserve ? Number(config[0].min_cash_reserve) : 0
    return JSON.stringify({
      total_cash_vnd: totalCash,
      reserve_vnd: reserve,
      deployable_vnd: Math.max(0, totalCash - reserve),
      max_risk_per_trade_vnd: config[0]?.max_risk_per_trade ? Number(config[0].max_risk_per_trade) : null,
      max_concurrent_positions: config[0]?.max_concurrent_positions ?? null,
    })
  },
}

// ─── Goal ─────────────────────────────────────────────────────────────────────

const get_goal: Tool = {
  description:
    'Get active trading goal — target amount, realized P&L, progress percentage, days remaining, and deadline.',
  inputSchema: z.object({}),
  execute: async () => {
    const sql = getSql()
    const rows = await sql`
      SELECT goal_name, target AS target_vnd, realized AS realized_vnd,
             progress_pct, deadline, days_remaining, required_daily_vnd, status
      FROM v_goal_progress
      ORDER BY deadline ASC
      LIMIT 1
    `
    return JSON.stringify(rows[0] ?? null)
  },
}

// ─── Learnings ────────────────────────────────────────────────────────────────

const get_learnings: Tool = {
  description:
    'Get trading performance stats from retrospective analysis — entry hit rate, win rate, avg P/L, and sample sizes.',
  inputSchema: z.object({}),
  execute: async () => {
    const sql = getSql()
    const rows = await sql`
      SELECT last_updated, rolling_window_days, total_days, total_recs,
             overall_entry_hit_rate, overall_win_rate, avg_pnl_percent
      FROM learnings_summary
      ORDER BY last_updated DESC
      LIMIT 1
    `
    return JSON.stringify(rows[0] ?? null)
  },
}

// ─── Export ───────────────────────────────────────────────────────────────────

export const portfolioTools = {
  get_portfolio,
  get_trades,
  get_cash,
  get_goal,
  get_learnings,
}
