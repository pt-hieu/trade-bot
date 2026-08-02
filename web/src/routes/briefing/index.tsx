import { createFileRoute } from '@tanstack/react-router'
import { useIntelDate, useDailyIntel, useRecommendations } from '../../hooks/use-intel'
import { MorningNarrative } from '../../components/briefing/morning/morning-narrative'
import { ErrorState } from '../../components/ui/error-state'
import { Skeleton } from '../../components/ui/skeleton'

export const Route = createFileRoute('/briefing/')({
  component: MorningPage,
  ssr: false,
})

function MorningPage() {
  const { activeDate } = useIntelDate()
  const { data: intel, isLoading: intelLoading, error: intelError, refetch: refetchIntel } = useDailyIntel(activeDate)
  const { data: recs, isLoading: recsLoading } = useRecommendations(activeDate)

  if (intelLoading && recsLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-20 w-full" />
        <div className="flex gap-3">
          <Skeleton className="h-24 flex-1" />
          <Skeleton className="h-24 flex-1" />
          <Skeleton className="h-24 flex-1" />
          <Skeleton className="h-24 flex-1" />
        </div>
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    )
  }

  if (intelError) {
    return (
      <ErrorState
        description="Could not load morning briefing. The analysis pipeline runs at 7 AM Vietnam time."
        retry={refetchIntel}
      />
    )
  }

  if (!intel && !recs) {
    return (
      <div className="text-center py-12 space-y-1">
        <p className="text-muted-foreground text-sm">No briefing data for this date.</p>
        <p className="text-muted-foreground/50 text-xs">The pipeline runs at 7 AM on trading days.</p>
      </div>
    )
  }

  return <MorningNarrative intel={(intel as any) ?? null} recs={(recs as any) ?? null} recsLoading={recsLoading} />
}
