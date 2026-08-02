import type { Trade } from '../types/index'
import type { Strategy } from './strategy'

export interface TickerTradeGroup {
  ticker: string
  trades: Trade[]
  openTrades: Trade[]
  closedTrades: Trade[]
  totalShares: number
  totalOpenShares: number
  tradeCount: number
  wins: number
  losses: number
  winRate: number | null
  netPlVnd: number
  netPlPct: number | null
  avgEntryPriceVnd: number
  strategies: Strategy[]
  firstEntryDate: string
  latestEntryDate: string
}

export interface GroupedTradesResult {
  openGroups: TickerTradeGroup[]
  closedGroups: TickerTradeGroup[]
  maxAbsolutePlVnd: number
  strategyCounts: Map<Strategy, number>
}

export function computeUnrealizedPl(
  currentPrice: number | null | undefined,
  avgEntryPrice: number,
  totalShares: number
): { unrealizedPlVnd: number | null; unrealizedPlPct: number | null } {
  if (!currentPrice || avgEntryPrice <= 0 || totalShares <= 0) {
    return { unrealizedPlVnd: null, unrealizedPlPct: null }
  }
  const unrealizedPlVnd = (currentPrice - avgEntryPrice) * totalShares
  const unrealizedPlPct = ((currentPrice - avgEntryPrice) / avgEntryPrice) * 100
  return { unrealizedPlVnd, unrealizedPlPct }
}

export function groupTradesByTicker(trades: Trade[]): GroupedTradesResult {
  const tickerMap = new Map<string, Trade[]>()
  const strategyCounts = new Map<Strategy, number>()

  for (const trade of trades) {
    const existing = tickerMap.get(trade.ticker) || []
    existing.push(trade)
    tickerMap.set(trade.ticker, existing)

    if (trade.strategy) {
      const strategy = trade.strategy as Strategy
      strategyCounts.set(strategy, (strategyCounts.get(strategy) || 0) + 1)
    }
  }

  const allGroups: TickerTradeGroup[] = []

  for (const [ticker, tickerTrades] of tickerMap) {
    const openTrades = tickerTrades.filter((trade) => trade.status === 'OPEN')
    const closedTrades = tickerTrades.filter((trade) => trade.status === 'CLOSED')

    const wins = closedTrades.filter((trade) => trade.result === 'WIN').length
    const losses = closedTrades.filter((trade) => trade.result === 'LOSS').length
    const closedCount = wins + losses

    const netPlVnd = closedTrades.reduce(
      (sum, trade) => sum + (Number(trade.pl_net_vnd) || 0),
      0
    )

    const totalBuyVnd = closedTrades.reduce(
      (sum, trade) => sum + (Number(trade.buy_total_vnd) || 0),
      0
    )

    const totalOpenShares = openTrades.reduce((sum, trade) => sum + Number(trade.shares), 0)
    const totalShares = tickerTrades.reduce((sum, trade) => sum + Number(trade.shares), 0)

    const openBuyTotal = openTrades.reduce(
      (sum, trade) => sum + Number(trade.buy_total_vnd),
      0
    )
    const avgEntryPriceVnd =
      totalOpenShares > 0 ? Math.round(openBuyTotal / totalOpenShares) : 0

    const strategies = [
      ...new Set(
        tickerTrades
          .map((trade) => trade.strategy)
          .filter((strategy): strategy is Strategy => strategy !== null)
      ),
    ]

    const dates = tickerTrades.map((trade) => trade.entry_date).sort()

    allGroups.push({
      ticker,
      trades: tickerTrades,
      openTrades,
      closedTrades,
      totalShares,
      totalOpenShares,
      tradeCount: tickerTrades.length,
      wins,
      losses,
      winRate: closedCount > 0 ? wins / closedCount : null,
      netPlVnd,
      netPlPct: totalBuyVnd > 0 ? (netPlVnd / totalBuyVnd) * 100 : null,
      avgEntryPriceVnd,
      strategies,
      firstEntryDate: dates[0] || '',
      latestEntryDate: dates[dates.length - 1] || '',
    })
  }

  const openGroups = allGroups
    .filter((group) => group.openTrades.length > 0)
    .sort((groupA, groupB) => groupB.totalOpenShares - groupA.totalOpenShares)

  const closedGroups = allGroups
    .filter((group) => group.openTrades.length === 0 && group.closedTrades.length > 0)
    .sort((groupA, groupB) => Math.abs(groupB.netPlVnd) - Math.abs(groupA.netPlVnd))

  const maxAbsolutePlVnd = Math.max(
    ...allGroups.map((group) => Math.abs(group.netPlVnd)),
    1
  )

  return { openGroups, closedGroups, maxAbsolutePlVnd, strategyCounts }
}

/** Filter pre-computed groups by strategy/ticker without re-grouping */
export function filterGroups(
  result: GroupedTradesResult,
  strategyFilter?: string,
  tickerFilter?: string
): GroupedTradesResult {
  if (!strategyFilter && !tickerFilter) return result

  const filterGroup = (group: TickerTradeGroup): boolean => {
    if (tickerFilter && group.ticker !== tickerFilter.toUpperCase()) return false
    if (strategyFilter && !group.trades.some((trade) => trade.strategy === strategyFilter))
      return false
    return true
  }

  const openGroups = result.openGroups.filter(filterGroup)
  const closedGroups = result.closedGroups.filter(filterGroup)
  const maxAbsolutePlVnd = Math.max(
    ...openGroups.map((group) => Math.abs(group.netPlVnd)),
    ...closedGroups.map((group) => Math.abs(group.netPlVnd)),
    1
  )

  return { openGroups, closedGroups, maxAbsolutePlVnd, strategyCounts: result.strategyCounts }
}
