import { createServerFn } from '@tanstack/react-start'
import { getSql } from '../db'
import { fetchEnhancedHoldings } from './portfolio-analytics'
import type {
  PortfolioMetrics,
  SectorConcentration,
  PositionSizingViolation,
} from '../../types/index'

export const getPortfolioMetrics = createServerFn({ method: 'GET' }).handler(async (): Promise<PortfolioMetrics> => {
  const sql = getSql()

  const [sectorRows, openTradeStats, closedStats, configRows] = await Promise.all([
    sql`
      SELECT
        sector_name,
        SUM(market_value_vnd)::bigint AS market_value_vnd
      FROM v_portfolio_current
      WHERE holding_type != 'Cash' AND market_value_vnd > 0
      GROUP BY sector_name
      ORDER BY market_value_vnd DESC
    `,
    sql`
      SELECT
        AVG(CURRENT_DATE - entry_date)::int AS avg_days_held,
        (SELECT ticker FROM trades_calculated WHERE status = 'OPEN' ORDER BY entry_date ASC LIMIT 1) AS longest_ticker,
        (SELECT entry_date::text FROM trades_calculated WHERE status = 'OPEN' ORDER BY entry_date ASC LIMIT 1) AS longest_entry_date,
        (SELECT (CURRENT_DATE - entry_date)::int FROM trades_calculated WHERE status = 'OPEN' ORDER BY entry_date ASC LIMIT 1) AS longest_days
      FROM trades_calculated
      WHERE status = 'OPEN'
    `,
    sql`
      SELECT
        COUNT(CASE WHEN pl_net_vnd > 0 THEN 1 END)::int AS wins,
        COUNT(CASE WHEN pl_net_vnd <= 0 THEN 1 END)::int AS losses,
        COALESCE(AVG(CASE WHEN pl_net_vnd > 0 THEN pl_pct END), 0)::numeric AS avg_win_pct,
        COALESCE(AVG(CASE WHEN pl_net_vnd <= 0 THEN pl_pct END), 0)::numeric AS avg_loss_pct
      FROM trades_calculated
      WHERE status = 'CLOSED'
    `,
    sql`SELECT concentration_exit_pct FROM trading_config LIMIT 1`,
  ])

  // fetchEnhancedHoldings runs sequentially to avoid concurrent connection limit in Workers runtime
  const enhancedHoldings = await fetchEnhancedHoldings(sql)

  const totalMarketValue = sectorRows.reduce((sum, row) => sum + Number(row.market_value_vnd), 0)

  const sectors: SectorConcentration[] = sectorRows.map((row) => ({
    sectorName: String(row.sector_name || 'Unknown'),
    marketValueVnd: Number(row.market_value_vnd),
    weightPct: totalMarketValue > 0
      ? Math.round((Number(row.market_value_vnd) / totalMarketValue) * 1000) / 10
      : 0,
  }))

  // HHI = sum of squared weight percentages (threshold: >2500 Concentrated, >1500 Moderate)
  const herfindahlIndex = Math.round(
    sectors.reduce((sum, sector) => sum + sector.weightPct * sector.weightPct, 0)
  )
  const concentrationLabel = herfindahlIndex > 2500 ? 'Concentrated'
    : herfindahlIndex > 1500 ? 'Moderate'
    : 'Diversified'

  const longestOpen = openTradeStats[0]?.longest_ticker
    ? { ticker: String(openTradeStats[0].longest_ticker), days: Number(openTradeStats[0].longest_days), entryDate: String(openTradeStats[0].longest_entry_date) }
    : null

  const worstPosition = enhancedHoldings.reduce<{ ticker: string; plPct: number } | null>(
    (worst, holding) => {
      if (worst === null || holding.plPct < worst.plPct) {
        return { ticker: holding.ticker, plPct: holding.plPct }
      }
      return worst
    },
    null
  )

  const alignedCount = enhancedHoldings.filter((holding) => holding.systemAligned).length
  const totalCount = enhancedHoldings.length

  // Portfolio heat: positions within 5% of stop
  const heatCount = enhancedHoldings.filter(
    (holding) => holding.vsStopPct !== null && holding.vsStopPct < 5
  ).length

  const concentrationLimit = Number(configRows[0]?.concentration_exit_pct) || 30
  const tickerWeights = new Map<string, number>()
  for (const holding of enhancedHoldings) {
    const current = tickerWeights.get(holding.ticker) || 0
    tickerWeights.set(holding.ticker, current + holding.weightPct)
  }
  const positionViolations: PositionSizingViolation[] = []
  for (const [ticker, weightPct] of tickerWeights) {
    if (weightPct > concentrationLimit) {
      positionViolations.push({ ticker, weightPct, limitPct: concentrationLimit })
    }
  }

  const wins = Number(closedStats[0]?.wins) || 0
  const losses = Number(closedStats[0]?.losses) || 0

  return {
    sectors,
    herfindahlIndex,
    concentrationLabel,
    avgDaysHeld: Number(openTradeStats[0]?.avg_days_held) || 0,
    longestOpen,
    maxDrawdown: worstPosition,
    systemAlignmentPct: totalCount > 0 ? Math.round((alignedCount / totalCount) * 100) : 0,
    systemAlignedCount: alignedCount,
    systemTotalCount: totalCount,
    portfolioHeatCount: heatCount,
    portfolioHeatTotal: totalCount,
    closedWins: wins,
    closedLosses: losses,
    closedWinRate: (wins + losses) > 0 ? Math.round((wins / (wins + losses)) * 1000) / 10 : 0,
    avgWinPct: Math.round(Number(closedStats[0]?.avg_win_pct) * 10) / 10,
    avgLossPct: Math.round(Number(closedStats[0]?.avg_loss_pct) * 10) / 10,
    positionViolations,
    marketValue: totalMarketValue,
    costBasis: enhancedHoldings.reduce((sum, holding) => sum + holding.costBasisVnd, 0),
  }
})
