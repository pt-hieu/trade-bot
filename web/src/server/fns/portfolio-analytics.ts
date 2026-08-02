import { createServerFn } from '@tanstack/react-start'
import { getSql } from '../db'
import { getHistoryBatch } from '../vnstock'
import type {
  PortfolioSummary,
  EnhancedHolding,
} from '../../types/index'

export const getPortfolioSummary = createServerFn({ method: 'GET' }).handler(async (): Promise<PortfolioSummary> => {
  const sql = getSql()

  const ytdStart = `${new Date().getFullYear()}-01-01`
  const today = new Date().toISOString().slice(0, 10)

  const [portfolioAgg, closedAgg, lastUpdatedRows, vnindexMap] = await Promise.all([
    sql`
      SELECT
        COALESCE(SUM(CASE WHEN holding_type != 'Cash' THEN market_value_vnd END), 0)::bigint AS market_value,
        COALESCE(SUM(CASE WHEN holding_type != 'Cash' THEN cost_basis_vnd END), 0)::bigint AS cost_basis,
        COUNT(CASE WHEN holding_type != 'Cash' THEN 1 END)::int AS position_count,
        COALESCE(MAX(CASE WHEN holding_type = 'Cash' THEN avg_cost_vnd END), 0)::bigint AS cash_available
      FROM v_portfolio_current
    `,
    sql`
      SELECT
        COALESCE(SUM(pl_net_vnd), 0)::bigint AS realized_pl,
        COUNT(*)::int AS closed_count
      FROM trades_calculated
      WHERE status = 'CLOSED'
    `,
    sql`SELECT MAX(updated_at)::text AS last_updated FROM portfolio_holdings`,
    getHistoryBatch(['VNINDEX'], ytdStart, today),
  ])

  const marketValue = Number(portfolioAgg[0].market_value)
  const costBasis = Number(portfolioAgg[0].cost_basis)
  const cashAvailable = Number(portfolioAgg[0].cash_available)
  const positionCount = Number(portfolioAgg[0].position_count)
  const realizedPl = Number(closedAgg[0].realized_pl)
  const closedTradeCount = Number(closedAgg[0].closed_count)

  const unrealizedPl = marketValue - costBasis
  const unrealizedPlPct = costBasis > 0 ? (unrealizedPl / costBasis) * 100 : 0
  const totalReturn = unrealizedPl + realizedPl
  const totalReturnPct = costBasis > 0 ? (totalReturn / costBasis) * 100 : 0
  const cashDeployedPct = (costBasis + cashAvailable) > 0
    ? (costBasis / (costBasis + cashAvailable)) * 100
    : 0

  const vnindexBars = vnindexMap['VNINDEX'] ?? []
  let vnindexReturnPct = 0
  if (vnindexBars.length >= 2) {
    const firstClose = vnindexBars[0].close
    const lastClose = vnindexBars[vnindexBars.length - 1].close
    vnindexReturnPct = firstClose > 0 ? ((lastClose - firstClose) / firstClose) * 100 : 0
  }

  const alphaVsVnindex = totalReturnPct - vnindexReturnPct
  const unrealizedTrend: 'up' | 'down' | 'flat' = unrealizedPl > 0 ? 'up' : unrealizedPl < 0 ? 'down' : 'flat'

  return {
    marketValue,
    costBasis,
    unrealizedPl,
    unrealizedPlPct,
    unrealizedTrend,
    realizedPl,
    closedTradeCount,
    totalReturn,
    totalReturnPct,
    alphaVsVnindex,
    vnindexReturnPct,
    cashAvailable,
    cashDeployedPct,
    positionCount,
    lastUpdated: lastUpdatedRows[0]?.last_updated || null,
  }
})

export async function fetchEnhancedHoldings(existingSql?: ReturnType<typeof getSql>): Promise<EnhancedHolding[]> {
  const sql = existingSql ?? getSql()

  const rows = await sql`
    WITH current_prices AS (
      SELECT DISTINCT ON (ticker)
        ticker,
        current_price_vnd,
        sector_name
      FROM (
        SELECT h.ticker, h.current_price_vnd, s.name AS sector_name
        FROM portfolio_holdings h
        LEFT JOIN stocks st ON h.ticker = st.ticker
        LEFT JOIN sectors s ON st.sector_id = s.id
        WHERE h.holding_type != 'Cash' AND h.shares > 0
      ) sub
      ORDER BY ticker
    ),
    total_market AS (
      SELECT COALESCE(SUM(t.shares * cp.current_price_vnd), 1) AS total
      FROM trades_calculated t
      JOIN current_prices cp ON cp.ticker = t.ticker
      WHERE t.status = 'OPEN'
    ),
    latest_stops AS (
      SELECT DISTINCT ON (dr.ticker)
        dr.ticker,
        dr.stop_price_vnd
      FROM daily_recommendations dr
      JOIN daily_records rec ON rec.id = dr.record_id
      WHERE dr.stop_price_vnd IS NOT NULL
        AND dr.stop_price_vnd > 0
        AND dr.action IN ('BUY', 'ADD', 'HOLD', 'LIMIT_BUY')
      ORDER BY dr.ticker, rec.record_date DESC
    ),
    alignment AS (
      SELECT DISTINCT ON (t.id)
        t.id AS trade_id,
        CASE WHEN dr.id IS NOT NULL THEN true ELSE false END AS system_aligned
      FROM trades_calculated t
      LEFT JOIN daily_records rec ON rec.record_date = t.entry_date
      LEFT JOIN daily_recommendations dr ON dr.record_id = rec.id
        AND dr.ticker = t.ticker
        AND dr.action IN ('BUY', 'ADD', 'LIMIT_BUY')
      WHERE t.status = 'OPEN'
      ORDER BY t.id, dr.id DESC NULLS LAST
    )
    SELECT
      t.ticker,
      cp.sector_name,
      t.shares,
      t.entry_price_vnd AS avg_cost_vnd,
      cp.current_price_vnd,
      t.buy_total_vnd AS cost_basis_vnd,
      (t.shares * cp.current_price_vnd) AS market_value_vnd,
      (t.shares * cp.current_price_vnd - t.buy_total_vnd) AS pl_vnd,
      CASE
        WHEN t.buy_total_vnd > 0
        THEN ROUND(((t.shares * cp.current_price_vnd - t.buy_total_vnd)::numeric / t.buy_total_vnd) * 100, 2)
        ELSE 0
      END AS pl_pct,
      t.strategy,
      t.entry_date::text,
      t.plan_type,
      (CURRENT_DATE - t.entry_date)::int AS days_held,
      COALESCE(al.system_aligned, false) AS system_aligned,
      ls.stop_price_vnd,
      CASE
        WHEN ls.stop_price_vnd IS NOT NULL AND ls.stop_price_vnd > 0 AND cp.current_price_vnd IS NOT NULL
        THEN ROUND(((cp.current_price_vnd - ls.stop_price_vnd)::numeric / ls.stop_price_vnd) * 100, 1)
        ELSE NULL
      END AS vs_stop_pct,
      ROUND(((t.shares * cp.current_price_vnd)::numeric / tm.total) * 100, 1) AS weight_pct
    FROM trades_calculated t
    JOIN current_prices cp ON cp.ticker = t.ticker
    LEFT JOIN latest_stops ls ON ls.ticker = t.ticker
    LEFT JOIN alignment al ON al.trade_id = t.id
    CROSS JOIN total_market tm
    WHERE t.status = 'OPEN'
    ORDER BY (t.shares * cp.current_price_vnd) DESC
  `

  return rows.map((row) => ({
    ticker: String(row.ticker),
    sectorName: row.sector_name ? String(row.sector_name) : null,
    shares: Number(row.shares),
    avgCostVnd: Number(row.avg_cost_vnd),
    currentPriceVnd: row.current_price_vnd ? Number(row.current_price_vnd) : null,
    costBasisVnd: Number(row.cost_basis_vnd),
    marketValueVnd: Number(row.market_value_vnd),
    plVnd: Number(row.pl_vnd),
    plPct: Number(row.pl_pct),
    strategy: row.strategy ? String(row.strategy) : null,
    entryDate: row.entry_date ? String(row.entry_date) : null,
    planType: row.plan_type ? String(row.plan_type) : null,
    daysHeld: row.days_held != null ? Number(row.days_held) : null,
    systemAligned: Boolean(row.system_aligned),
    stopPriceVnd: row.stop_price_vnd ? Number(row.stop_price_vnd) : null,
    vsStopPct: row.vs_stop_pct != null ? Number(row.vs_stop_pct) : null,
    weightPct: Number(row.weight_pct),
  }))
}

export const getEnhancedHoldings = createServerFn({ method: 'GET' }).handler(
  async (): Promise<EnhancedHolding[]> => fetchEnhancedHoldings()
)
