import { createServerFn } from '@tanstack/react-start'
import { getSql } from '../db'
import { getHistoryBatch } from '../vnstock'
import {
  MIN_DATA_POINTS,
  RISK_FREE_RATE,
  buildWeightedReturns,
  calculateBeta,
  calculateSharpe,
  calculateSortino,
} from '../risk-metrics'

export const getMetrics = createServerFn({ method: 'GET' }).handler(async () => {
  const sql = getSql()
  const [metricsRows, extremesRows] = await Promise.all([
    sql`SELECT * FROM v_swing_metrics LIMIT 1`,
    sql`
      SELECT
        MAX(CASE WHEN pl_net_vnd > 0 THEN pl_net_vnd END) AS max_win_vnd,
        MIN(CASE WHEN pl_net_vnd < 0 THEN pl_net_vnd END) AS max_loss_vnd
      FROM trades_calculated
      WHERE status = 'CLOSED'
    `,
  ])

  if (metricsRows.length === 0) {
    throw new Error('No metrics found')
  }

  return {
    ...metricsRows[0],
    max_win_vnd: extremesRows[0]?.max_win_vnd ?? null,
    max_loss_vnd: extremesRows[0]?.max_loss_vnd ?? null,
  }
})

export const getMetricsByStrategy = createServerFn({ method: 'GET' }).handler(async () => {
  const sql = getSql()
  const rows = await sql`
    SELECT
      strategy,
      trades,
      wins,
      losses,
      win_rate,
      profit_factor,
      total_pl_vnd
    FROM v_metrics_by_strategy
    ORDER BY total_pl_vnd DESC
  `
  return rows
})

/** Compute daily return series from a sorted array of close prices. */
function computeReturns(bars: { close: number; time?: string }[]): Map<string, number> {
  const map = new Map<string, number>()
  for (let i = 1; i < bars.length; i++) {
    const prev = bars[i - 1].close
    if (prev === 0) continue
    const dateKey = bars[i].time?.slice(0, 10)
    if (dateKey) map.set(dateKey, (bars[i].close - prev) / prev)
  }
  return map
}

export const getRiskMetrics = createServerFn({ method: 'GET' }).handler(async () => {
  const sql = getSql()

  const holdingsRows = await sql`
    SELECT ticker, market_value_vnd
    FROM portfolio_holdings
    WHERE holding_type = 'Stock' AND shares > 0
  `

  const tickers = holdingsRows.map((r) => String(r.ticker))

  const end = new Date().toISOString().slice(0, 10)
  const start = new Date(Date.now() - 91 * 86_400_000).toISOString().slice(0, 10)
  const priceMap = await getHistoryBatch([...tickers, 'VNINDEX'], start, end)

  const marketReturns = computeReturns(priceMap['VNINDEX'] ?? [])
  const tickerMaps = new Map<string, Map<string, number>>()
  for (const ticker of tickers) {
    const bars = priceMap[ticker] ?? []
    if (bars.length > 1) tickerMaps.set(ticker, computeReturns(bars))
  }

  const tickerBetas: Record<string, number> = {}
  for (const [ticker, returns] of tickerMaps) {
    const beta = calculateBeta(returns, marketReturns)
    if (beta !== null) tickerBetas[ticker] = beta
  }

  const totalMarketValue = holdingsRows.reduce(
    (sum, r) => sum + Number(r.market_value_vnd),
    0,
  )
  const weights: Record<string, number> = {}
  if (totalMarketValue > 0) {
    for (const r of holdingsRows) {
      weights[String(r.ticker)] = Number(r.market_value_vnd) / totalMarketValue
    }
  }

  const portfolioReturnMap = buildWeightedReturns(weights, tickerMaps)
  const portfolioValues = [...portfolioReturnMap.values()]
  const dataPoints = portfolioValues.length

  if (dataPoints < MIN_DATA_POINTS) {
    return {
      data_points: dataPoints,
      minimum_required: MIN_DATA_POINTS,
      portfolio_beta: null,
      sharpe_ratio: null,
      sortino_ratio: null,
      ticker_betas: tickerBetas,
      risk_free_rate: RISK_FREE_RATE,
      message: `Insufficient data: ${dataPoints}/${MIN_DATA_POINTS} trading days.`,
    }
  }

  let portfolioBeta: number | null = null
  if (totalMarketValue > 0) {
    let weightedSum = 0
    let coveredWeight = 0
    for (const [ticker, weight] of Object.entries(weights)) {
      if (tickerBetas[ticker] !== undefined) {
        weightedSum += weight * tickerBetas[ticker]
        coveredWeight += weight
      }
    }
    if (coveredWeight >= 0.5) {
      portfolioBeta = Math.round((weightedSum / coveredWeight) * 1000) / 1000
    }
  }

  return {
    data_points: dataPoints,
    minimum_required: MIN_DATA_POINTS,
    portfolio_beta: portfolioBeta,
    sharpe_ratio: calculateSharpe(portfolioValues),
    sortino_ratio: calculateSortino(portfolioValues),
    ticker_betas: tickerBetas,
    risk_free_rate: RISK_FREE_RATE,
  }
})
