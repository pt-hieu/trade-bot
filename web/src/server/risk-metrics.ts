/**
 * Risk-adjusted return metrics: Beta, Sharpe, Sortino.
 *
 * Pure math functions — no DB, no side effects.
 * Ported from scripts/shared/risk_metrics.py.
 */

export const TRADING_DAYS_PER_YEAR = 252
export const RISK_FREE_RATE = 0.04 // ~4% Vietnam government bonds
export const MIN_DATA_POINTS = 20

/**
 * Align two return maps on common dates. Returns paired arrays.
 */
export function alignReturns(
  a: Map<string, number>,
  b: Map<string, number>,
): [number[], number[]] {
  const common = [...a.keys()].filter((d) => b.has(d)).sort()
  return [common.map((d) => a.get(d)!), common.map((d) => b.get(d)!)]
}

/**
 * Beta = Cov(Rp, Rm) / Var(Rm).
 * Returns null if insufficient data or zero market variance.
 */
export function calculateBeta(
  portfolioReturns: Map<string, number>,
  marketReturns: Map<string, number>,
): number | null {
  const [rp, rm] = alignReturns(portfolioReturns, marketReturns)
  const n = rp.length
  if (n < MIN_DATA_POINTS) return null

  const meanRp = rp.reduce((s, v) => s + v, 0) / n
  const meanRm = rm.reduce((s, v) => s + v, 0) / n

  let cov = 0
  let varRm = 0
  for (let i = 0; i < n; i++) {
    cov += (rp[i] - meanRp) * (rm[i] - meanRm)
    varRm += (rm[i] - meanRm) ** 2
  }
  cov /= n - 1
  varRm /= n - 1

  if (varRm === 0) return null
  return Math.round((cov / varRm) * 1000) / 1000
}

/**
 * Sharpe = (Annualized Return - Rf) / Annualized Volatility.
 * Returns null if insufficient data or zero volatility.
 */
export function calculateSharpe(
  returns: number[],
  riskFreeRate = RISK_FREE_RATE,
): number | null {
  const n = returns.length
  if (n < MIN_DATA_POINTS) return null

  const meanDaily = returns.reduce((s, v) => s + v, 0) / n
  const variance =
    returns.reduce((s, r) => s + (r - meanDaily) ** 2, 0) / (n - 1)
  const dailyStd = Math.sqrt(variance)

  if (dailyStd === 0) return null

  const annReturn = meanDaily * TRADING_DAYS_PER_YEAR
  const annVol = dailyStd * Math.sqrt(TRADING_DAYS_PER_YEAR)

  return Math.round(((annReturn - riskFreeRate) / annVol) * 1000) / 1000
}

/**
 * Build a weighted portfolio return series from per-ticker returns.
 * For each date, portfolio_return = sum(weight_i * return_i) / covered_weight.
 * Skips dates where tickers covering <50% of weight are missing.
 */
export function buildWeightedReturns(
  weights: Record<string, number>,
  tickerReturns: Map<string, Map<string, number>>,
): Map<string, number> {
  const allDates = new Set<string>()
  for (const returns of tickerReturns.values()) {
    for (const date of returns.keys()) allDates.add(date)
  }

  const result = new Map<string, number>()
  for (const date of [...allDates].sort()) {
    let weightedReturn = 0
    let coveredWeight = 0
    for (const [ticker, w] of Object.entries(weights)) {
      const tickerMap = tickerReturns.get(ticker)
      if (tickerMap?.has(date)) {
        weightedReturn += w * tickerMap.get(date)!
        coveredWeight += w
      }
    }
    if (coveredWeight >= 0.5) {
      result.set(date, weightedReturn / coveredWeight)
    }
  }
  return result
}

/**
 * Sortino = (Annualized Return - Rf) / Downside Deviation.
 * Downside deviation divides by total n (not downside count), guaranteeing Sortino >= Sharpe.
 * Returns null if insufficient data or no downside days.
 */
export function calculateSortino(
  returns: number[],
  riskFreeRate = RISK_FREE_RATE,
): number | null {
  const n = returns.length
  if (n < MIN_DATA_POINTS) return null

  const meanDaily = returns.reduce((s, v) => s + v, 0) / n
  const dailyRf = riskFreeRate / TRADING_DAYS_PER_YEAR

  const downsideSum = returns
    .filter((r) => r < dailyRf)
    .reduce((s, r) => s + (r - dailyRf) ** 2, 0)

  if (downsideSum === 0) return null

  const downsideDev = Math.sqrt(downsideSum / n)
  const annDD = downsideDev * Math.sqrt(TRADING_DAYS_PER_YEAR)

  if (annDD === 0) return null

  const annReturn = meanDaily * TRADING_DAYS_PER_YEAR
  return Math.round(((annReturn - riskFreeRate) / annDD) * 1000) / 1000
}
