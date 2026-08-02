import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getAlerts, getAlertBadgeCount, createAlert, updateAlert, deleteAlert, bulkCancelAlerts } from '../server/fns/alerts'
import type { AlertInput } from '../types'

/** Lightweight count for nav badge — polls every 2 min */
export function useAlertBadgeCount() {
  return useQuery({
    queryKey: ['alerts', 'badge-count'],
    queryFn: () => getAlertBadgeCount(),
    staleTime: 120_000,
    refetchInterval: 120_000,
  })
}

export function useAlerts(status?: string) {
  return useQuery({
    queryKey: ['alerts', status ?? 'all'],
    queryFn: () => getAlerts({ data: status ? { status } : {} }),
    staleTime: 60_000,
  })
}

export function useCreateAlert() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: AlertInput) => createAlert({ data: input }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })
}

export function useUpdateAlert() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: Partial<AlertInput> }) =>
      updateAlert({ data: { id, input } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })
}

export function useCancelAlert() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) => deleteAlert({ data: { id } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })
}

export function useBulkCancelAlerts() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (ids: string[]) => bulkCancelAlerts({ data: { ids } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })
}
