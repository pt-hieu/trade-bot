import { useQuery } from '@tanstack/react-query'
import { getLearnings } from '../server/fns/learnings'

export function useLearnings() {
  return useQuery({
    queryKey: ['learnings'],
    queryFn: () => getLearnings(),
    staleTime: 5 * 60 * 1000,
  })
}
