/**
 * Chat tool registry — Vercel AI SDK v6 tool definitions.
 * All tools execute server-side via direct Neon SQL queries.
 * Minimal set: portfolio, trades, watchlist, alerts, market context, prices.
 */
import { z } from 'zod'
import { getSql } from '../../server/db'
import type { Tool } from 'ai'
import { getLatestPrices } from '../../server/vnstock'

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
  render: z.boolean().optional().describe('Set true to render a trades table in the chat'),
})

const get_trades: Tool = {
  description:
    'Get recent trades. Default returns latest 10 trades (open + closed). Set all=true for full history.',
  inputSchema: _tradesSchema,
  execute: async (input: z.infer<typeof _tradesSchema>) => {
    const { all, status } = input
    const sql = getSql()
    const limit = all ? 100 : 10
    const rows = status && status !== 'all'
      ? await sql`
          SELECT id, ticker, plan_type, strategy, entry_date, entry_price_vnd,
                 exit_date, exit_price_vnd, shares, buy_total_vnd, pl_net_vnd, pl_pct,
                 days_held, result, status
          FROM v_recent_trades
          WHERE status = ${status}
          ORDER BY entry_date DESC
          LIMIT ${limit}
        `
      : await sql`
          SELECT id, ticker, plan_type, strategy, entry_date, entry_price_vnd,
                 exit_date, exit_price_vnd, shares, buy_total_vnd, pl_net_vnd, pl_pct,
                 days_held, result, status
          FROM v_recent_trades
          ORDER BY entry_date DESC
          LIMIT ${limit}
        `
    return JSON.stringify(rows)
  },
}

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
  description: 'Get active price/technical alerts. INFORMATIONAL — alerts are registered by automated pipeline agents (morning brief, midday check) using their own reasoning and data snapshots. Treat as leads to cross-verify against current data, not pre-validated recommendations.',
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

// ─── Market Context ───────────────────────────────────────────────────────────

const get_market_context: Tool = {
  description:
    'Get latest market regime (RISK_ON/NEUTRAL/RISK_OFF), VN-Index level, macro metrics (VIX, DXY, USD/VND), and hot/cold sectors.',
  inputSchema: z.object({
    render: z.boolean().optional().describe('Set true to render a market context card in the chat'),
  }),
  execute: async () => {
    const sql = getSql()
    const [regimeRows, macroRows, rotationRows, vnidxPrices] = await Promise.all([
      sql`
        SELECT mr.regime, mr.regime_confidence, mr.key_signal
        FROM market_regimes mr
        ORDER BY mr.scan_date DESC LIMIT 1
      `,
      sql`
        SELECT dxy_value, dxy_change_pct, vix_value, vix_change_pct,
               usd_vnd_rate, global_risk_regime, interpretation
        FROM macro_metrics ORDER BY scan_date DESC LIMIT 1
      `,
      sql`
        SELECT s.name AS sector_name, srd.classification, srd.return_pct
        FROM sector_rotations sr
        JOIN sector_rotation_details srd ON srd.rotation_id = sr.id
        JOIN sectors s ON srd.sector_id = s.id
        WHERE sr.scan_date = (SELECT MAX(scan_date) FROM sector_rotations)
        ORDER BY srd.classification, srd.return_pct DESC
      `,
      getLatestPrices('VNINDEX'),
    ])

    const regime = regimeRows[0]
    const macro = macroRows[0]
    const dailyReturn = vnidxPrices
      ? (vnidxPrices.close - vnidxPrices.prev_close) / vnidxPrices.prev_close
      : null

    return JSON.stringify({
      regime: regime
        ? {
            regime: regime.regime,
            confidence: regime.regime_confidence,
            key_signal: regime.key_signal,
            vn_index: vnidxPrices ? vnidxPrices.close : null,
            vn_index_change_pct: dailyReturn !== null ? dailyReturn * 100 : null,
          }
        : null,
      macro: macro ?? null,
      sectors: {
        hot: rotationRows
          .filter((r) => r.classification === 'hot')
          .map((r) => ({ sector: r.sector_name, return_pct: r.return_pct })),
        cold: rotationRows
          .filter((r) => r.classification === 'cold')
          .map((r) => ({ sector: r.sector_name, return_pct: r.return_pct })),
      },
    })
  },
}

// ─── Prices ───────────────────────────────────────────────────────────────────

const _pricesSchema = z.object({
  ticker: z.string().describe('Stock ticker symbol, e.g. "FPT", "VNM", "HPG"'),
  days: z.number().optional().describe('Number of days of history (default: 60, max: 200)'),
  render: z.boolean().optional().describe('Set true to render an interactive candlestick chart in the chat'),
})

const get_prices: Tool = {
  description:
    'Get OHLCV price history for a Vietnamese stock ticker. Returns daily candles (up to 90 days). Use for chart analysis, support/resistance, and trend identification.',
  inputSchema: _pricesSchema,
  execute: async (input: z.infer<typeof _pricesSchema>) => {
    const { ticker, days = 60 } = input
    const apiUrl = process.env.VNSTOCK_API_URL
    if (!apiUrl) return JSON.stringify({ error: 'VNSTOCK_API_URL not configured' })

    const end = new Date().toISOString().slice(0, 10)
    const lookback = Math.min(days, 200)
    const start = new Date(Date.now() - lookback * 86_400_000).toISOString().slice(0, 10)

    try {
      const url = new URL('/quote/history', apiUrl)
      url.searchParams.set('symbol', ticker.toUpperCase())
      url.searchParams.set('interval', '1D')
      url.searchParams.set('start', start)
      url.searchParams.set('end', end)

      const res = await fetch(url.toString(), { signal: AbortSignal.timeout(15_000) })
      if (!res.ok) return JSON.stringify({ error: `API returned ${res.status}` })
      const data = await res.json()
      return JSON.stringify(data)
    } catch (e) {
      return JSON.stringify({ error: String(e) })
    }
  },
}

// ─── Export ───────────────────────────────────────────────────────────────────

export const chatTools = {
  get_portfolio,
  get_trades,
  get_watchlist,
  get_alerts,
  get_market_context,
  get_prices,
}
