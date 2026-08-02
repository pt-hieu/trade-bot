import { TableRow, TableCell } from '../ui/table'
import { toTitleCase } from '../../lib/utils'
import type { ConvictionLevel } from '../../types/index'
import { formatRelativeTime, formatShortDate } from '../../lib/date'
import dayjs from 'dayjs'

export function formatDate(dateStr: string) {
  const diffHrs = dayjs().diff(dayjs(dateStr), 'hour')
  if (diffHrs < 24) return formatRelativeTime(dateStr)
  return formatShortDate(dateStr)
}

export const CONVICTION_CLASS: Record<ConvictionLevel, string> = {
  'High': 'bg-emerald-600 hover:bg-emerald-600/90 text-white',
  'Medium-High': 'bg-blue-600 hover:bg-blue-600/90 text-white',
  'Medium': '',
  'Medium-Low': 'bg-amber-600 hover:bg-amber-600/90 text-white',
  'Low': 'bg-zinc-600 hover:bg-zinc-600/90 text-white',
}

export function groupBySector<T extends { sector_name: string }>(items: T[]) {
  const groups = new Map<string, T[]>()
  for (const item of items) {
    const arr = groups.get(item.sector_name) ?? []
    arr.push(item)
    groups.set(item.sector_name, arr)
  }
  return groups
}

export function SectorGroup({
  sector,
  colSpan,
  children,
}: {
  sector: string
  colSpan: number
  children: React.ReactNode
}) {
  return (
    <>
      <TableRow className="hover:bg-transparent">
        <TableCell
          colSpan={colSpan}
          className="py-2 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground"
        >
          {toTitleCase(sector)}
        </TableCell>
      </TableRow>
      {children}
    </>
  )
}

export const TIER_CONFIG: Record<number, { label: string; badgeClass: string }> = {
  1: { label: 'Core', badgeClass: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20' },
  2: { label: 'Growth', badgeClass: 'bg-blue-500/15 text-blue-400 border-blue-500/20' },
  3: { label: 'Spec', badgeClass: 'bg-zinc-500/15 text-zinc-400 border-zinc-500/20' },
}

export { ColumnInfo } from '../ui/column-info'

