/**
 * Market domain tools — regime, prices, technicals, macro, flow, sector rotation.
 */
import { z } from 'zod'
import type { Tool } from 'ai'
import { getSql, VNSTOCK_API_URL } from './shared'
import { computeDailyReturn, getLatestPrices, getTechnicals, computeRS } from '../../../server/vnstock'

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
  render: z
    .boolean()
    .optional()
    .describe('Set true to render an interactive candlestick chart in the chat'),
})

const get_prices: Tool = {
  description:
    'Get OHLCV price history for a Vietnamese stock ticker. Returns daily candles (up to 200 days). Use for chart analysis, support/resistance, and trend identification.',
  inputSchema: _pricesSchema,
  execute: async (input: z.infer<typeof _pricesSchema>) => {
    const { ticker, days = 60 } = input
    const apiUrl = VNSTOCK_API_URL
    if (!apiUrl) return JSON.stringify({ error: 'VNSTOCK_API_URL not configured' })

    const end = new Date().toISOString().slice(0, 10)
    const lookback = Math.min(days, 200)
    const start = new Date(Date.now() - lookback * 86_400_000).toISOString().slice(0, 10)

    try {
      const url = new URL(`${apiUrl}/quote/history`)
      url.searchParams.set('symbol', ticker.toUpperCase())
      url.searchParams.set('interval', '1D')
      url.searchParams.set('start', start)
      url.searchParams.set('end', end)

      const res = await fetch(url.toString(), { signal: AbortSignal.timeout(15_000) })
      if (!res.ok) return JSON.stringify({ error: `API returned ${res.status}` })
      return JSON.stringify(await res.json())
    } catch (e) {
      return JSON.stringify({ error: String(e) })
    }
  },
}

// ─── Technicals ───────────────────────────────────────────────────────────────

const _technicalsSchema = z.object({
  ticker: z.string().describe('Stock ticker symbol, e.g. "FPT"'),
})

const get_technicals: Tool = {
  description:
    'Get latest technical indicators for a ticker: RSI, MA20/50, MACD, Bollinger Bands, ATR, ADX, Stochastic, Supertrend, volume stats, and trend classification.',
  inputSchema: _technicalsSchema,
  execute: async (input: z.infer<typeof _technicalsSchema>) => {
    const data = await getTechnicals(input.ticker)
    return JSON.stringify(data ?? null)
  },
}

// ─── Foreign Flow ─────────────────────────────────────────────────────────────

const _flowSchema = z.object({
  ticker: z.string().describe('Stock ticker symbol'),
  days: z.number().optional().describe('Days of flow history to fetch (default: 10)'),
})

const get_flow: Tool = {
  description:
    'Get foreign investor, proprietary, and retail net buy/sell flow for a ticker. Key indicator for institutional interest.',
  inputSchema: _flowSchema,
  execute: async (input: z.infer<typeof _flowSchema>) => {
    const { ticker, days = 10 } = input
    const apiUrl = VNSTOCK_API_URL
    if (!apiUrl) return JSON.stringify({ error: 'VNSTOCK_API_URL not configured' })

    try {
      const url = new URL(`${apiUrl}/enrichment/flow`)
      url.searchParams.set('symbol', ticker.toUpperCase())
      url.searchParams.set('days', String(days))
      const res = await fetch(url.toString(), { signal: AbortSignal.timeout(10_000) })
      if (!res.ok) return JSON.stringify({ error: `API returned ${res.status}` })
      return JSON.stringify(await res.json())
    } catch (e) {
      return JSON.stringify({ error: String(e) })
    }
  },
}

// ─── Relative Strength ────────────────────────────────────────────────────────

const get_relative_strength: Tool = {
  description:
    'Get 20-day relative strength (RS) of a ticker vs VN-Index. RS > 1 means outperforming the market.',
  inputSchema: z.object({
    ticker: z.string().describe('Stock ticker symbol'),
  }),
  execute: async (input: { ticker: string }) => {
    const rs = await computeRS(input.ticker)
    if (rs === null) return JSON.stringify(null)
    return JSON.stringify({ ticker: input.ticker.toUpperCase(), rs_20d: rs })
  },
}

// ─── Export ───────────────────────────────────────────────────────────────────

export const marketTools = {
  get_market_context,
  get_prices,
  get_technicals,
  get_flow,
  get_relative_strength,
}
