import { useQuery } from '@tanstack/react-query'
import { getRiskMetrics } from '../server/fns/metrics'

export function useRiskMetrics() {
  return useQuery({
    queryKey: ['risk-metrics'],
    queryFn: () => getRiskMetrics(),
    staleTime: 60_000,
  })
}
