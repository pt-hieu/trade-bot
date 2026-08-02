/**
 * Watchlist domain tools — watchlist, alerts, catalysts, events, insider.
 */
import { z } from 'zod'
import type { Tool } from 'ai'
import { getSql, VNSTOCK_API_URL } from './shared'

// ─── Watchlist ────────────────────────────────────────────────────────────────

const get_watchlist: Tool = {
  description: 'Get swing watchlist tickers with RSI, sector, and notes. Sorted by sector then ticker.',
  inputSchema: z.object({
    render: z.boolean().optional().describe('Set true to render a watchlist table in the chat'),
  }),
  execute: async () => {
    const sql = getSql()
    const rows = await sql`
      SELECT sw.ticker, s.name AS sector_name, sw.stock_type,
             sw.rsi, sw.notes, sw.is_pinned, sw.pin_reason
      FROM swing_watchlist sw
      JOIN sectors s ON sw.sector_id = s.id
      WHERE sw.is_active = TRUE
      ORDER BY s.name, sw.ticker
    `
    return JSON.stringify(rows)
  },
}

// ─── Alerts ───────────────────────────────────────────────────────────────────

const _alertsSchema = z.object({
  ticker: z.string().optional().describe('Filter alerts by ticker (e.g. "FPT")'),
  render: z.boolean().optional().describe('Set true to render alerts as cards in the chat'),
})

const get_alerts: Tool = {
  description: 'Get active price/technical alerts with conditions, recommended action, and priority.',
  inputSchema: _alertsSchema,
  execute: async (input: z.infer<typeof _alertsSchema>) => {
    const { ticker } = input
    const sql = getSql()
    const rows = ticker
      ? await sql`
          SELECT a.ticker, a.recommended_action, a.priority, a.rationale,
                 a.entry_price, a.stop_price, a.target_price, a.status, a.created_at,
                 COALESCE(json_agg(
                   json_build_object('type', ac.condition_type, 'value', ac.condition_value::float)
                   ORDER BY ac.sort_order
                 ) FILTER (WHERE ac.id IS NOT NULL), '[]') AS conditions
          FROM alerts a
          LEFT JOIN alert_conditions ac ON ac.alert_id = a.id
          WHERE a.status = 'active' AND a.ticker = ${ticker.toUpperCase()}
          GROUP BY a.id
          ORDER BY a.created_at DESC
          LIMIT 20
        `
      : await sql`
          SELECT a.ticker, a.recommended_action, a.priority, a.rationale,
                 a.entry_price, a.stop_price, a.target_price, a.status, a.created_at,
                 COALESCE(json_agg(
                   json_build_object('type', ac.condition_type, 'value', ac.condition_value::float)
                   ORDER BY ac.sort_order
                 ) FILTER (WHERE ac.id IS NOT NULL), '[]') AS conditions
          FROM alerts a
          LEFT JOIN alert_conditions ac ON ac.alert_id = a.id
          WHERE a.status = 'active'
          GROUP BY a.id
          ORDER BY a.created_at DESC
          LIMIT 20
        `
    return JSON.stringify(rows)
  },
}

// ─── Catalysts ────────────────────────────────────────────────────────────────

const get_catalysts: Tool = {
  description:
    'Get active catalysts for tickers — upcoming earnings, product launches, regulatory approvals, or other price-moving events.',
  inputSchema: z.object({
    ticker: z.string().optional().describe('Filter by ticker, or omit for all active catalysts'),
  }),
  execute: async (input: { ticker?: string }) => {
    const sql = getSql()
    const rows = input.ticker
      ? await sql`
          SELECT catalyst_type, event AS description, expected AS expected_date,
                 confidence AS conviction, status, affected_tickers, notes
          FROM catalysts
          WHERE status = 'active'
            AND pipeline_version = 'v2'
            AND affected_tickers @> ARRAY[${input.ticker.toUpperCase()}]
          ORDER BY added_date DESC
          LIMIT 10
        `
      : await sql`
          SELECT catalyst_type, event AS description, expected AS expected_date,
                 confidence AS conviction, status, affected_tickers, notes
          FROM catalysts
          WHERE status = 'active'
            AND pipeline_version = 'v2'
          ORDER BY added_date DESC
          LIMIT 20
        `
    return JSON.stringify(rows)
  },
}

// ─── Capital Events ───────────────────────────────────────────────────────────

const get_capital_events: Tool = {
  description:
    'Get upcoming corporate capital events — dividends, rights issues, stock splits, AGM dates.',
  inputSchema: z.object({
    ticker: z.string().optional().describe('Filter by ticker, or omit for all upcoming events'),
    days: z.number().optional().describe('Lookahead days (default: 30)'),
  }),
  execute: async (input: { ticker?: string; days?: number }) => {
    const sql = getSql()
    const lookahead = input.days ?? 30
    const rows = input.ticker
      ? await sql`
          SELECT ticker, event_type, expected_date AS event_date, description, amount, status
          FROM capital_events
          WHERE ticker = ${input.ticker.toUpperCase()}
            AND status NOT IN ('completed', 'cancelled')
            AND (expected_date IS NULL OR expected_date::date >= CURRENT_DATE)
            AND (expected_date IS NULL OR expected_date::date <= CURRENT_DATE + ${lookahead} * INTERVAL '1 day')
          ORDER BY expected_date ASC
        `
      : await sql`
          SELECT ticker, event_type, expected_date AS event_date, description, amount, status
          FROM capital_events
          WHERE status NOT IN ('completed', 'cancelled')
            AND (expected_date IS NULL OR expected_date::date >= CURRENT_DATE)
            AND (expected_date IS NULL OR expected_date::date <= CURRENT_DATE + ${lookahead} * INTERVAL '1 day')
          ORDER BY expected_date ASC
          LIMIT 30
        `
    return JSON.stringify(rows)
  },
}

// ─── Insider Transactions ─────────────────────────────────────────────────────

const get_insider: Tool = {
  description:
    'Get recent insider buy/sell transactions for a ticker (last 90 days). Shows executive/director trading activity.',
  inputSchema: z.object({
    ticker: z.string().describe('Stock ticker symbol'),
  }),
  execute: async (input: { ticker: string }) => {
    const apiUrl = VNSTOCK_API_URL
    if (!apiUrl) return JSON.stringify({ error: 'VNSTOCK_API_URL not configured' })

    try {
      const url = new URL(`${apiUrl}/enrichment/insider`)
      url.searchParams.set('symbol', input.ticker.toUpperCase())
      url.searchParams.set('days', '90')
      const res = await fetch(url.toString(), { signal: AbortSignal.timeout(10_000) })
      if (!res.ok) return JSON.stringify({ error: `API returned ${res.status}` })
      return JSON.stringify(await res.json())
    } catch (e) {
      return JSON.stringify({ error: String(e) })
    }
  },
}

// ─── Export ───────────────────────────────────────────────────────────────────

export const watchlistTools = {
  get_watchlist,
  get_alerts,
  get_catalysts,
  get_capital_events,
  get_insider,
}
