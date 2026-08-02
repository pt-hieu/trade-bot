import { createFileRoute } from '@tanstack/react-router'
import { useIntelDate, useMiddayCheck } from '../../hooks/use-intel'
import { MiddaySection } from '../../components/briefing/midday-section'
import { ErrorState } from '../../components/ui/error-state'
import { Skeleton } from '../../components/ui/skeleton'

export const Route = createFileRoute('/briefing/midday')({
  component: MiddayPage,
  ssr: false,
})

function MiddayPage() {
  const { activeDate } = useIntelDate()
  const { data: midday, isLoading, error, refetch } = useMiddayCheck(activeDate)

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    )
  }

  if (error) {
    return (
      <ErrorState
        description="Could not load midday check. The midday analysis runs at 12 PM on trading days."
        retry={refetch}
      />
    )
  }

  if (!midday) {
    return (
      <div className="text-center py-12 space-y-1">
        <p className="text-muted-foreground text-sm">No midday check for this date.</p>
        <p className="text-muted-foreground/50 text-xs">Midday checks run at 12 PM Vietnam time during market break.</p>
      </div>
    )
  }

  return <MiddaySection data={midday as any} />
}
