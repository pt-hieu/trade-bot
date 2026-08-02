import { createServerFn } from '@tanstack/react-start'
import { getSql } from '../db'
import { getHistoryBatch } from '../vnstock'
import type {
  PortfolioSnapshot,
  TradeEvent,
  DateHolding,
  VnindexDataPoint,
  PortfolioHistoryResponse,
} from '../../types/index'

export const getPortfolio = createServerFn({ method: 'GET' }).handler(async () => {
  const sql = getSql()
  const rows = await sql`
    SELECT
      ticker,
      holding_type,
      shares,
      avg_cost_vnd,
      current_price_vnd,
      cost_basis_vnd,
      market_value_vnd,
      pl_vnd,
      pl_pct,
      sector_name
    FROM v_portfolio_current
    ORDER BY market_value_vnd DESC
  `
  return rows
})

/** Build ticker → date → close_vnd lookup from priceMap (API prices in thousands VND → VND). */
function buildPriceLookup(
  priceMap: Record<string, { time: string; close: number }[]>,
): Map<string, Map<string, number>> {
  const lookup = new Map<string, Map<string, number>>()
  for (const [ticker, bars] of Object.entries(priceMap)) {
    const dateMap = new Map<string, number>()
    for (const bar of bars) {
      const dateStr = bar.time?.slice(0, 10)
      if (dateStr && bar.close > 0) dateMap.set(dateStr, Math.round(bar.close * 1000))
    }
    lookup.set(ticker, dateMap)
  }
  return lookup
}

/** Reconstruct daily portfolio market value from trades + price history. */
function computeSnapshots(
  tradeRows: { ticker: string; entry_date: string; exit_date: string | null; shares: number }[],
  priceMap: Record<string, { time: string; close: number }[]>,
): PortfolioSnapshot[] {
  const lookup = buildPriceLookup(priceMap)

  const allDates = new Set<string>()
  for (const bars of Object.values(priceMap)) {
    for (const bar of bars) {
      const dateStr = bar.time?.slice(0, 10)
      if (dateStr) allDates.add(dateStr)
    }
  }

  const snapshots: PortfolioSnapshot[] = []

  for (const date of [...allDates].sort()) {
    let total = 0
    let hasPrice = false

    for (const trade of tradeRows) {
      if (trade.entry_date > date) continue
      if (trade.exit_date !== null && trade.exit_date <= date) continue

      const tickerMap = lookup.get(trade.ticker)
      if (!tickerMap) continue

      // Fallback to most recent prior price if today's is missing
      let price = tickerMap.get(date)
      if (price === undefined) {
        const sortedDates = [...tickerMap.keys()].sort()
        for (const d of sortedDates) {
          if (d <= date) price = tickerMap.get(d)
          else break
        }
      }

      if (price !== undefined) {
        total += trade.shares * price
        hasPrice = true
      }
    }

    if (hasPrice) {
      snapshots.push({ snapshot_date: date, invested_value_vnd: total })
    }
  }

  return snapshots
}

export const getPortfolioHistory = createServerFn({ method: 'GET' }).handler(async (): Promise<PortfolioHistoryResponse> => {
  const sql = getSql()

  const [tradeRows, tradeEvents] = await Promise.all([
    sql`
      SELECT ticker, entry_date::text, exit_date::text, shares
      FROM trades_calculated
      WHERE entry_date IS NOT NULL
    `,
    sql`
      SELECT entry_date::text AS date, ticker, 'BUY' AS action, shares, plan_type
      FROM trades_calculated
      WHERE entry_date IS NOT NULL
      UNION ALL
      SELECT exit_date::text AS date, ticker, 'SELL' AS action, shares, plan_type
      FROM trades_calculated
      WHERE exit_date IS NOT NULL AND status = 'CLOSED'
      ORDER BY date
    `,
  ])

  const tickers = [...new Set(tradeRows.map((row) => String(row.ticker)))]
  let snapshots: PortfolioSnapshot[] = []
  let vnindex: VnindexDataPoint[] = []

  if (tickers.length > 0) {
    const minDate = tradeRows.reduce(
      (min, row) => (String(row.entry_date) < min ? String(row.entry_date) : min),
      String(tradeRows[0].entry_date),
    )
    const maxDate = new Date().toISOString().slice(0, 10)

    const priceMap = await getHistoryBatch([...tickers, 'VNINDEX'], minDate, maxDate)

    const trades = tradeRows.map((row) => ({
      ticker: String(row.ticker),
      entry_date: String(row.entry_date),
      exit_date: row.exit_date !== null ? String(row.exit_date) : null,
      shares: Number(row.shares),
    }))

    snapshots = computeSnapshots(trades, priceMap)

    // Normalize VN-Index to portfolio scale
    const vnindexBars = priceMap['VNINDEX'] ?? []
    if (vnindexBars.length > 0 && snapshots.length > 0) {
      const firstPortfolioValue = snapshots[0].invested_value_vnd
      const firstVnindexClose = vnindexBars[0].close * 1000
      const scaleFactor = firstVnindexClose > 0 ? firstPortfolioValue / firstVnindexClose : 1

      const vnindexDateMap = new Map<string, number>()
      for (const bar of vnindexBars) {
        const dateStr = bar.time?.slice(0, 10)
        if (dateStr) vnindexDateMap.set(dateStr, Math.round(bar.close * 1000 * scaleFactor))
      }

      vnindex = snapshots
        .map((snapshot) => {
          const value = vnindexDateMap.get(snapshot.snapshot_date)
          if (value === undefined) return null
          return { snapshotDate: snapshot.snapshot_date, value }
        })
        .filter(Boolean) as VnindexDataPoint[]
    }
  }

  return { snapshots, trades: tradeEvents as TradeEvent[], vnindex }
})

export const getHoldingsAt = createServerFn({ method: 'GET' })
  .inputValidator((data: { date: string }) => data)
  .handler(async ({ data }) => {
    const sql = getSql()

    const tradeRows = await sql`
      SELECT
        t.ticker,
        SUM(t.shares)::INT AS shares,
        t.plan_type
      FROM trades_calculated t
      WHERE t.entry_date <= ${data.date}::date
        AND (t.exit_date IS NULL OR t.exit_date > ${data.date}::date)
      GROUP BY t.ticker, t.plan_type
    `

    if (!tradeRows.length) return [] as DateHolding[]

    const tickers = [...new Set(tradeRows.map((row) => String(row.ticker)))]
    const priceMap = await getHistoryBatch(tickers, data.date, data.date)

    const result: DateHolding[] = tradeRows
      .flatMap((row) => {
        const ticker = String(row.ticker)
        const bars = priceMap[ticker] ?? []
        const closeRaw = bars[bars.length - 1]?.close ?? null
        if (closeRaw === null) return []
        const closeVnd = Math.round(closeRaw * 1000)
        const shares = Number(row.shares)
        return [
          {
            ticker,
            shares,
            plan_type: row.plan_type as 'SWING' | 'LONGTERM',
            close_vnd: closeVnd,
            market_value_vnd: shares * closeVnd,
          },
        ]
      })
      .sort((a, b) => b.market_value_vnd - a.market_value_vnd)

    return result
  })

export const updateCash = createServerFn({ method: 'POST' })
  .inputValidator((data: { amount_vnd: number }) => data)
  .handler(async ({ data }) => {
    const sql = getSql()

    const rows = await sql`
      UPDATE portfolio_holdings
      SET avg_cost_vnd = ${data.amount_vnd}, updated_at = NOW()
      WHERE UPPER(ticker) = 'CASH' AND holding_type = 'Cash'
      RETURNING avg_cost_vnd
    `

    if (rows.length === 0) throw new Error('Cash record not found')

    return { amount_vnd: Number(rows[0].avg_cost_vnd), updated: true }
  })
