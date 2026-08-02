import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getPortfolio,
  getPortfolioHistory,
  getHoldingsAt,
  updateCash,
} from '../server/fns/portfolio'
import { getPortfolioSummary, getEnhancedHoldings } from '../server/fns/portfolio-analytics'
import { getPortfolioMetrics } from '../server/fns/portfolio-metrics'

export function usePortfolioSummary() {
  return useQuery({
    queryKey: ['portfolio', 'summary'],
    queryFn: () => getPortfolioSummary(),
    staleTime: 60_000,
  })
}

export function useEnhancedHoldings() {
  return useQuery({
    queryKey: ['portfolio', 'enhanced-holdings'],
    queryFn: () => getEnhancedHoldings(),
    staleTime: 60_000,
  })
}

export function usePortfolioMetrics() {
  return useQuery({
    queryKey: ['portfolio', 'metrics'],
    queryFn: () => getPortfolioMetrics(),
    staleTime: 60_000,
  })
}

export function usePortfolio() {
  return useQuery({
    queryKey: ['portfolio'],
    queryFn: () => getPortfolio(),
    staleTime: 60_000,
  })
}

export function usePortfolioHistory() {
  return useQuery({
    queryKey: ['portfolio', 'history'],
    queryFn: () => getPortfolioHistory(),
    staleTime: 60_000,
  })
}

export function useHoldingsAt(date: string | null) {
  return useQuery({
    queryKey: ['portfolio', 'holdings-at', date],
    queryFn: () => getHoldingsAt({ data: { date: date! } }),
    enabled: !!date,
  })
}

export function useUpdateCash() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (amount_vnd: number) => updateCash({ data: { amount_vnd } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portfolio'] })
    },
  })
}
