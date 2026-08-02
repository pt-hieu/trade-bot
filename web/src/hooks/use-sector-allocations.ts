import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getSectorAllocations, upsertSectorAllocation, deleteSectorAllocation } from '../server/fns/config'
import type { SectorAllocation } from '../types'

export function useSectorAllocations() {
  return useQuery({
    queryKey: ['sector-allocations'],
    queryFn: () => getSectorAllocations(),
  })
}

export function useUpsertSectorAllocation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { sector_name: string; target_pct: number }) =>
      upsertSectorAllocation({ data: input }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sector-allocations'] })
    },
  })
}

export function useDeleteSectorAllocation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sector_name: string) => deleteSectorAllocation({ data: { sector_name } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sector-allocations'] })
    },
  })
}
