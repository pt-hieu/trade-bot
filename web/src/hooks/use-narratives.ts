import { useQuery } from '@tanstack/react-query'
import { getNarratives } from '../server/fns/narratives'

export function useNarratives(params?: {
  status?: string
  type?: string
  ticker?: string
}) {
  return useQuery({
    queryKey: ['narratives', params?.status, params?.type, params?.ticker],
    queryFn: () =>
      getNarratives({
        data: {
          status: params?.status ?? null,
          type: params?.type ?? null,
          ticker: params?.ticker ?? null,
        },
      }),
    staleTime: 60_000,
  })
}
