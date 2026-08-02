import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getTradingConfig, updateTradingConfig } from '../server/fns/config'
import type { TradingConfig } from '../types'

export function useTradingConfig() {
  return useQuery({
    queryKey: ['trading-config'],
    queryFn: () => getTradingConfig(),
  })
}

export function useUpdateTradingConfig() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: Partial<TradingConfig>) => updateTradingConfig({ data: input }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trading-config'] })
    },
  })
}
