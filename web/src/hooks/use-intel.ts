import { useQuery } from '@tanstack/react-query'
import { useSearch } from '@tanstack/react-router'
import { getScanDates, getDailyIntel, getRecommendations, getMiddayCheck } from '../server/fns/intel'

/** Read ?date= from URL, fall back to latest scan date */
export function useIntelDate() {
  const search = useSearch({ strict: false }) as { date?: string }
  const { data: scanDates, isLoading } = useScanDates()
  const dateParam = search.date
  const activeDate = dateParam ?? scanDates?.[0]
  return { activeDate, scanDates, isLoading }
}

export function useScanDates() {
  return useQuery({
    queryKey: ['intel', 'scan-dates'],
    queryFn: () => getScanDates(),
    staleTime: 60_000,
  })
}

export function useDailyIntel(date?: string) {
  return useQuery({
    queryKey: ['intel', 'daily', date],
    queryFn: () => getDailyIntel({ data: date ? { date } : {} }),
    enabled: true,
    staleTime: 60_000,
  })
}

export function useRecommendations(date?: string) {
  return useQuery({
    queryKey: ['intel', 'recommendations', date],
    queryFn: () => getRecommendations({ data: { date: date! } }),
    enabled: !!date,
    staleTime: 60_000,
  })
}

export function useMiddayCheck(date?: string) {
  return useQuery({
    queryKey: ['intel', 'midday', date],
    queryFn: () => getMiddayCheck({ data: { date: date! } }),
    enabled: !!date,
  })
}
