import { createFileRoute, Outlet } from '@tanstack/react-router'
import { Suspense } from 'react'
import { Spinner } from '../../components/ui/spinner'
import { BriefingLayoutInner } from '../../components/briefing/briefing-layout-inner'

export const Route = createFileRoute('/briefing')({
  validateSearch: (search: Record<string, unknown>) => ({
    date: (search.date as string) ?? undefined,
  }),
  component: IntelLayout,
  ssr: false,
})

function IntelLayout() {
  return (
    <Suspense
      fallback={
        <main className="min-h-[calc(100dvh-77px)] p-6 max-w-7xl mx-auto flex items-center justify-center">
          <Spinner />
        </main>
      }
    >
      <BriefingLayoutInner>
        <Outlet />
      </BriefingLayoutInner>
    </Suspense>
  )
}
