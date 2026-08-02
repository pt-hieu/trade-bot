import { useQuery } from '@tanstack/react-query'
import { getChartHistory, getChartTechnicals } from '../server/fns/chart'
import type { ChartInterval } from '../types/chart'

export function useChartHistory(ticker: string | null, interval: ChartInterval = '1D') {
  return useQuery({
    queryKey: ['chart', 'history', ticker, interval],
    queryFn: () =>
      getChartHistory({ data: { symbol: ticker!, interval } }),
    staleTime: interval === '1D' ? 5 * 60_000 : 60_000,
    enabled: !!ticker,
  })
}

export function useChartTechnicals(ticker: string | null) {
  return useQuery({
    queryKey: ['chart', 'technicals', ticker],
    queryFn: () => getChartTechnicals({ data: { symbol: ticker! } }),
    staleTime: 5 * 60_000,
    enabled: !!ticker,
  })
}
