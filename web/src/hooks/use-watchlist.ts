import { useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getWatchlist, getWatchlistSectors, addToWatchlist,
  refreshWatchlistRsi, updateWatchlistItem, removeFromWatchlist,
} from '../server/fns/watchlist'
import { getCompanyResearch } from '../server/fns/research'
import { getPortfolio } from '../server/fns/portfolio'
import { mergeWatchlists, groupByReadiness, HOT_URGENCY_THRESHOLD } from '../lib/watchlist-merge'
import { useCurrentPrices, useSparklineData } from './use-sparkline-data'
import type { SwingWatchlistItem, LongtermWatchlistItem, WatchlistAddInput, WatchlistEditInput, WatchlistRemoveInput } from '../types'

// ─── Raw Data Hooks ──────────────────────────────────────────────────────────

export function useSwingWatchlist() {
  return useQuery({
    queryKey: ['watchlist', 'swing'],
    queryFn: () => getWatchlist({ data: { type: 'swing' } }),
    staleTime: 60_000,
  })
}

export function useLongtermWatchlist() {
  return useQuery({
    queryKey: ['watchlist', 'longterm'],
    queryFn: () => getWatchlist({ data: { type: 'longterm' } }),
    staleTime: 60_000,
  })
}

export function useSectors() {
  return useQuery({
    queryKey: ['sectors'],
    queryFn: () => getWatchlistSectors(),
    staleTime: 60_000,
  })
}

// ─── Mutations ───────────────────────────────────────────────────────────────

export function useAddToWatchlist() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: WatchlistAddInput) => addToWatchlist({ data: input }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['watchlist'] }) },
  })
}

export function useUpdateRsi() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (ticker: string) => refreshWatchlistRsi({ data: { ticker } }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['watchlist', 'swing'] }) },
  })
}

export function useEditWatchlistItem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: WatchlistEditInput) => updateWatchlistItem({ data: input }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['watchlist'] }) },
  })
}

export function useRemoveFromWatchlist() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: WatchlistRemoveInput) => removeFromWatchlist({ data: input }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['watchlist'] }) },
  })
}

export function useCompanyResearch(ticker: string | null) {
  return useQuery({
    queryKey: ['research', ticker],
    queryFn: () => getCompanyResearch({ data: { ticker: ticker! } }),
    enabled: !!ticker,
  })
}

// ─── Unified Watchlist ───────────────────────────────────────────────────────

/** Portfolio holdings as ticker → shares map. */
export function usePortfolioHoldings() {
  const { data: holdingsRaw, isLoading } = useQuery({
    queryKey: ['portfolio'],
    queryFn: () => getPortfolio(),
    staleTime: 60_000,
  })

  const holdingsMap = useMemo(() => {
    if (!holdingsRaw) return undefined
    const map = new Map<string, number>()
    for (const holding of holdingsRaw as any[]) {
      const existing = map.get(holding.ticker) || 0
      map.set(holding.ticker, existing + Number(holding.shares))
    }
    return map
  }, [holdingsRaw])

  return { data: holdingsMap, isLoading }
}

/** Merged, readiness-tiered watchlist from both swing + longterm sources. */
export function useUnifiedWatchlist() {
  const swing = useSwingWatchlist()
  const longterm = useLongtermWatchlist()
  const { data: holdingsMap } = usePortfolioHoldings()

  const allTickers = useMemo(() => {
    const tickers = new Set<string>()
    for (const item of (swing.data ?? []) as SwingWatchlistItem[]) tickers.add(item.ticker)
    for (const item of (longterm.data ?? []) as LongtermWatchlistItem[]) tickers.add(item.ticker)
    return [...tickers]
  }, [swing.data, longterm.data])

  // Lightweight prices (days=2) for ALL tickers — needed for readiness computation
  const { data: prices } = useCurrentPrices(allTickers)

  const unified = useMemo(() => {
    if (!swing.data || !longterm.data) return undefined
    return mergeWatchlists({
      swingItems: swing.data as SwingWatchlistItem[],
      longtermItems: longterm.data as LongtermWatchlistItem[],
      prices,
      holdings: holdingsMap,
    })
  }, [swing.data, longterm.data, prices, holdingsMap])

  const grouped = useMemo(() => {
    if (!unified) return undefined
    return groupByReadiness(unified)
  }, [unified])

  // Full 30d sparklines only for above-the-fold tickers (near_entry + hot setting_up)
  const chartTickers = useMemo(() => {
    if (!unified) return []
    return unified
      .filter((item) =>
        item.readiness === 'near_entry' ||
        (item.readiness === 'setting_up' && item.urgencyScore >= HOT_URGENCY_THRESHOLD),
      )
      .map((item) => item.ticker)
  }, [unified])

  const { data: sparklines, isLoading: sparklinesLoading } = useSparklineData(chartTickers)

  return {
    items: unified,
    grouped,
    sparklines,
    sparklinesLoading,
    isLoading: swing.isLoading || longterm.isLoading,
    error: swing.error || longterm.error,
    refetch: () => { swing.refetch(); longterm.refetch() },
  }
}
