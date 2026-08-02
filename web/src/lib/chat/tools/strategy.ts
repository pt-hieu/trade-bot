/**
 * Strategy domain tools — trade setups, simulation, rules, patterns, similar days.
 */
import { z } from 'zod'
import type { Tool } from 'ai'
import { getSql, VNSTOCK_API_URL } from './shared'

// ─── Trade Setup ──────────────────────────────────────────────────────────────

const compute_trade_setup: Tool = {
  description:
    'Compute R:R ratio and position sizing for a potential trade given entry, stop loss, and target levels. Returns risk amount, reward amount, R:R ratio, and suggested position size.',
  inputSchema: z.object({
    ticker: z.string().describe('Stock ticker symbol'),
    entry_vnd: z.number().describe('Entry price in VND (full, e.g. 42000)'),
    stop_vnd: z.number().describe('Stop loss price in VND'),
    target_vnd: z.number().describe('Target price in VND'),
    capital_vnd: z.number().optional().describe('Capital to deploy (default: uses deployable cash)'),
  }),
  execute: async (input: {
    ticker: string
    entry_vnd: number
    stop_vnd: number
    target_vnd: number
    capital_vnd?: number
  }) => {
    const sql = getSql()

    // Get deployable cash if capital not provided
    let capital = input.capital_vnd
    if (!capital) {
      const [cashRows, configRows] = await Promise.all([
        sql`SELECT market_value_vnd AS total_cash_vnd FROM v_portfolio_current WHERE ticker = 'CASH' LIMIT 1`,
        sql`SELECT min_cash_reserve FROM trading_config LIMIT 1`,
      ])
      const totalCash = cashRows[0]?.total_cash_vnd ? Number(cashRows[0].total_cash_vnd) : 0
      const reserve = configRows[0]?.min_cash_reserve ? Number(configRows[0].min_cash_reserve) : 0
      capital = Math.max(0, totalCash - reserve)
    }

    // Get max risk per trade from config
    const config = await sql`
      SELECT max_risk_per_trade FROM trading_config LIMIT 1
    `
    const maxRisk = config[0]?.max_risk_per_trade ? Number(config[0].max_risk_per_trade) : 2_000_000
    // Compute max allocation as capital fraction (for position sizing cap)
    const maxPct = capital > 0 ? Math.min(maxRisk / capital * 10, 0.3) : 0.15

    const risk = input.entry_vnd - input.stop_vnd
    const reward = input.target_vnd - input.entry_vnd
    const rr = risk > 0 ? reward / risk : 0

    const maxCapital = capital * maxPct
    const shares = risk > 0 ? Math.floor(maxCapital / input.entry_vnd / 100) * 100 : 0
    const cost = shares * input.entry_vnd
    const riskAmount = shares * Math.abs(risk)
    const rewardAmount = shares * reward

    return JSON.stringify({
      ticker: input.ticker.toUpperCase(),
      entry_vnd: input.entry_vnd,
      stop_vnd: input.stop_vnd,
      target_vnd: input.target_vnd,
      risk_per_share: risk,
      reward_per_share: reward,
      rr_ratio: Math.round(rr * 100) / 100,
      suggested_shares: shares,
      cost_vnd: cost,
      risk_amount_vnd: riskAmount,
      reward_amount_vnd: rewardAmount,
      max_capital_vnd: maxCapital,
    })
  },
}

// ─── Similar Days ─────────────────────────────────────────────────────────────

const get_similar_days: Tool = {
  description:
    'Find historical market days similar to today using vector similarity search. Returns dates, what happened, and how they resolved. Useful for "has this pattern happened before?" analysis.',
  inputSchema: z.object({
    limit: z.number().optional().describe('Number of similar days to return (default: 5)'),
  }),
  execute: async (input: { limit?: number }) => {
    const sql = getSql()
    const limit = input.limit ?? 5
    // Get most recent daily record embedding and find similar
    const rows = await sql`
      SELECT dr.record_date AS scan_date, dr.market_regime AS regime,
             dr.key_insight AS brief_summary,
             1 - (dr.context_embedding <=> latest.context_embedding) AS similarity
      FROM daily_records dr
      CROSS JOIN (
        SELECT context_embedding FROM daily_records
        WHERE context_embedding IS NOT NULL
        ORDER BY record_date DESC LIMIT 1
      ) latest
      WHERE dr.context_embedding IS NOT NULL
        AND dr.record_date < (SELECT MAX(record_date) FROM daily_records)
      ORDER BY similarity DESC
      LIMIT ${limit}
    `
    return JSON.stringify(rows)
  },
}

// ─── Trading Rules ────────────────────────────────────────────────────────────

const get_trading_rules: Tool = {
  description:
    'Get applicable trading rules and guidelines learned from past experience. Covers entry criteria, position sizing, exit rules, and regime-specific guidelines.',
  inputSchema: z.object({
    topic: z.string().optional().describe('Filter by topic keyword, e.g. "entry" or "stop loss"'),
  }),
  execute: async (input: { topic?: string }) => {
    const sql = getSql()
    const apiUrl = VNSTOCK_API_URL

    // Try API first, fall back to DB on any failure
    if (apiUrl) {
      try {
        const url = new URL('/memory/rules', apiUrl)
        if (input.topic) url.searchParams.set('topic', input.topic)
        const res = await fetch(url.toString(), { signal: AbortSignal.timeout(10_000) })
        if (res.ok) return JSON.stringify(await res.json())
      } catch { /* fall through to DB */ }
    }

    // DB fallback — always available
    const rows = input.topic
      ? await sql`
          SELECT rule_name, rule_type AS category, description AS rule_text,
                 action, confidence, created_at
          FROM trading_rules
          WHERE description ILIKE ${'%' + input.topic + '%'}
             OR rule_name ILIKE ${'%' + input.topic + '%'}
          ORDER BY confidence DESC LIMIT 10
        `
      : await sql`
          SELECT rule_name, rule_type AS category, description AS rule_text,
                 action, confidence, created_at
          FROM trading_rules
          ORDER BY confidence DESC LIMIT 15
        `
    return JSON.stringify(rows)
  },
}

// ─── Winning Patterns ─────────────────────────────────────────────────────────

const get_winning_patterns: Tool = {
  description:
    'Get patterns from historical winning trades — common setups, entry conditions, and market regimes that led to profitable outcomes.',
  inputSchema: z.object({}),
  execute: async () => {
    const sql = getSql()
    const rows = await sql`
      SELECT pattern_type AS category, pattern_description AS pattern_text,
             win_rate, loss_rate, sample_size, actionable_rule
      FROM learning_patterns
      WHERE win_rate >= 0.6 AND sample_size >= 3
      ORDER BY win_rate DESC, sample_size DESC
      LIMIT 10
    `
    return JSON.stringify(rows)
  },
}

// ─── Losing Patterns ──────────────────────────────────────────────────────────

const get_losing_patterns: Tool = {
  description:
    'Get patterns from historical losing trades — common setups, entry mistakes, and conditions to avoid.',
  inputSchema: z.object({}),
  execute: async () => {
    const sql = getSql()
    const rows = await sql`
      SELECT pattern_type AS category, pattern_description AS pattern_text,
             win_rate, loss_rate, sample_size, avoid_rule
      FROM learning_patterns
      WHERE loss_rate >= 0.6 AND sample_size >= 3
      ORDER BY loss_rate DESC, sample_size DESC
      LIMIT 10
    `
    return JSON.stringify(rows)
  },
}

// ─── Export ───────────────────────────────────────────────────────────────────

export const strategyTools = {
  compute_trade_setup,
  get_similar_days,
  get_trading_rules,
  get_winning_patterns,
  get_losing_patterns,
}
