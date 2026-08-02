import { useQuery } from '@tanstack/react-query'
import { getMetrics, getMetricsByStrategy } from '../server/fns/metrics'

export function useSwingMetrics() {
  return useQuery({
    queryKey: ['swing-metrics'],
    queryFn: () => getMetrics(),
    staleTime: 60_000,
  })
}

export function useMetricsByStrategy() {
  return useQuery({
    queryKey: ['metrics-by-strategy'],
    queryFn: () => getMetricsByStrategy(),
    staleTime: 60_000,
  })
}
