import type { PortfolioSnapshot, VnindexDataPoint } from '../../types/index'

export type TimeRange = '1M' | '3M' | 'YTD' | 'ALL'

export const TIME_RANGES: TimeRange[] = ['1M', '3M', 'YTD', 'ALL']

export function filterByTimeRange(snapshots: PortfolioSnapshot[], range: TimeRange): PortfolioSnapshot[] {
  if (range === 'ALL') return snapshots

  const now = new Date()
  let cutoff: Date

  switch (range) {
    case '1M':
      cutoff = new Date(now.getFullYear(), now.getMonth() - 1, now.getDate())
      break
    case '3M':
      cutoff = new Date(now.getFullYear(), now.getMonth() - 3, now.getDate())
      break
    case 'YTD':
      cutoff = new Date(now.getFullYear(), 0, 1)
      break
  }

  const cutoffStr = cutoff.toISOString().slice(0, 10)
  return snapshots.filter((snapshot) => snapshot.snapshot_date >= cutoffStr)
}

export function buildVnindexLookup(
  vnindex: VnindexDataPoint[],
  filteredSnapshots: PortfolioSnapshot[],
): Map<string, number> {
  if (vnindex.length === 0 || filteredSnapshots.length === 0) return new Map()

  // Server already normalizes VN-Index to portfolio scale.
  // With dual Y-axis each series auto-scales, so just build a date→value map
  // for the filtered date range.
  const firstDate = filteredSnapshots[0].snapshot_date
  const lastDate = filteredSnapshots[filteredSnapshots.length - 1].snapshot_date

  const lookup = new Map<string, number>()
  for (const entry of vnindex) {
    if (entry.snapshotDate >= firstDate && entry.snapshotDate <= lastDate) {
      lookup.set(entry.snapshotDate, entry.value)
    }
  }
  return lookup
}
