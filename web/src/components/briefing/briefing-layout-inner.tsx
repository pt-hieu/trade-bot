import { useCallback, type ReactNode } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { useScanDates } from '../../hooks/use-intel'
import { DateNav } from './date-nav'
import { BriefingPillToggle } from './section-nav'
import { Spinner } from '../ui/spinner'

export function BriefingLayoutInner({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as { date?: string }
  const { data: scanDates, isLoading } = useScanDates()

  const dateParam = search?.date
  const activeDate = dateParam ?? scanDates?.[0]

  const handleDateChange = useCallback(
    (date: string) => {
      navigate({ search: (prev: any) => ({ ...prev, date }), replace: true } as any)
    },
    [navigate]
  )

  if (isLoading) {
    return (
      <main className="min-h-[calc(100dvh-77px)] p-6 max-w-7xl mx-auto flex items-center justify-center">
        <Spinner />
      </main>
    )
  }

  if (!scanDates?.length) {
    return (
      <main className="min-h-[calc(100dvh-77px)] p-6 max-w-7xl mx-auto">
        <div className="text-center py-20">
          <p className="text-muted-foreground text-sm">No scan data available yet.</p>
          <p className="text-zinc-500 text-xs mt-1">Pipeline runs at 7 AM Vietnam time.</p>
        </div>
      </main>
    )
  }

  return (
    <main className="min-h-[calc(100dvh-77px)] max-w-7xl mx-auto p-6">
      <div className="flex items-center justify-between mb-6 h-[77px]">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold tracking-tight">Briefing</h1>
          <BriefingPillToggle />
        </div>
        <DateNav
          dates={scanDates}
          current={activeDate!}
          onChange={handleDateChange}
        />
      </div>

      <div className="min-w-0">
        {children}
      </div>
    </main>
  )
}
