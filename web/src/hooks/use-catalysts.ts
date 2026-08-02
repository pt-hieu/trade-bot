import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getCatalysts, createCatalyst, updateCatalyst, deleteCatalyst } from '../server/fns/catalysts'
import { getCapitalEvents, createCapitalEvent, updateCapitalEvent, deleteCapitalEvent } from '../server/fns/capital-events'
import type {
  CatalystInput,
  CapitalEventInput,
} from '../types'

// --- Catalysts ---

export function useCatalysts() {
  return useQuery({
    queryKey: ['catalysts'],
    queryFn: () => getCatalysts(),
  })
}

export function useCreateCatalyst() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CatalystInput) => createCatalyst({ data: input }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['catalysts'] })
    },
  })
}

export function useUpdateCatalyst() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: Partial<CatalystInput> }) =>
      updateCatalyst({ data: { id, ...input } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['catalysts'] })
    },
  })
}

export function useDeleteCatalyst() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteCatalyst({ data: { id } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['catalysts'] })
    },
  })
}

// --- Capital Events ---

export function useCapitalEvents() {
  return useQuery({
    queryKey: ['capital-events'],
    queryFn: () => getCapitalEvents(),
  })
}

export function useCreateCapitalEvent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CapitalEventInput) => createCapitalEvent({ data: input }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['capital-events'] })
    },
  })
}

export function useUpdateCapitalEvent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: Partial<CapitalEventInput> }) =>
      updateCapitalEvent({ data: { id, ...input } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['capital-events'] })
    },
  })
}

export function useDeleteCapitalEvent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteCapitalEvent({ data: { id } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['capital-events'] })
    },
  })
}
