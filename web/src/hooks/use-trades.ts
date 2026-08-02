import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getTrades, createTrade, updateTrade, deleteTrade } from '../server/fns/trades'
import type { TradeInput } from '../types'

export function useTrades() {
  return useQuery({
    queryKey: ['trades', 'recent'],
    queryFn: () => getTrades({ data: {} }),
    staleTime: 60_000,
  })
}

export function useAllTrades() {
  return useQuery({
    queryKey: ['trades', 'all'],
    queryFn: () => getTrades({ data: { all: true } }),
    staleTime: 60_000,
  })
}

export function useCreateTrade() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: TradeInput) => createTrade({ data: input }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trades'] })
      queryClient.invalidateQueries({ queryKey: ['swing-metrics'] })
      queryClient.invalidateQueries({ queryKey: ['portfolio'] })
      queryClient.invalidateQueries({ queryKey: ['goals'] })
    },
  })
}

export function useUpdateTrade() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: Partial<TradeInput> }) =>
      updateTrade({ data: { id, input } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trades'] })
      queryClient.invalidateQueries({ queryKey: ['swing-metrics'] })
      queryClient.invalidateQueries({ queryKey: ['portfolio'] })
      queryClient.invalidateQueries({ queryKey: ['goals'] })
    },
  })
}

export function useDeleteTrade() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) => deleteTrade({ data: { id } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trades'] })
      queryClient.invalidateQueries({ queryKey: ['swing-metrics'] })
      queryClient.invalidateQueries({ queryKey: ['portfolio'] })
      queryClient.invalidateQueries({ queryKey: ['goals'] })
    },
  })
}
