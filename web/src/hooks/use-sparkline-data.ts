import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getChartHistoryBatch } from '../server/fns/chart'
import { extractCurrentPrice } from '../lib/watchlist-utils'
import type { OhlcvBar } from '../types/chart'

type BatchResponse = Record<string, { data: OhlcvBar[]; count: number }>

/** 30-day OHLCV sparkline data — use only for tickers that need chart rendering. */
export function useSparklineData(tickers: string[]) {
  const sortedKey = [...tickers].sort().join(',')

  return useQuery({
    queryKey: ['sparklines', sortedKey],
    queryFn: async () => {
      const raw = await getChartHistoryBatch({ data: { symbols: sortedKey, days: 30 } }) as BatchResponse
      const result: Record<string, { close: number }[]> = {}
      for (const [ticker, entry] of Object.entries(raw)) {
        result[ticker] = entry.data.map((bar) => ({ close: Number(bar.close) }))
      }
      return result
    },
    staleTime: 10 * 60 * 1000,
    enabled: tickers.length > 0,
  })
}

/** Lightweight current prices — fetches only last 2 bars instead of 30 days. */
export function useCurrentPrices(tickers: string[]) {
  const sortedKey = [...tickers].sort().join(',')

  const { data: raw, isLoading } = useQuery({
    queryKey: ['current-prices', sortedKey],
    queryFn: async () => {
      return await getChartHistoryBatch({ data: { symbols: sortedKey, days: 2 } }) as BatchResponse
    },
    staleTime: 5 * 60 * 1000,
    enabled: tickers.length > 0,
  })

  const prices = useMemo(() => {
    if (!raw) return undefined
    const map = new Map<string, number>()
    for (const [ticker, entry] of Object.entries(raw)) {
      const bars = entry.data.map((bar) => ({ close: Number(bar.close) }))
      const price = extractCurrentPrice(bars)
      if (price != null) map.set(ticker, price)
    }
    return map
  }, [raw])

  return { data: prices, isLoading }
}
