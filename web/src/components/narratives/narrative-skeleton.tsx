import { Skeleton } from '../ui/skeleton'

function NarrativeCardSkeleton() {
  return (
    <div className="flex rounded-lg border border-border/40 overflow-hidden">
      <div className="w-[3px] bg-muted/40 shrink-0" />
      <div className="flex-1 px-3 py-2 space-y-1.5">
        <Skeleton className="h-4 w-4/5" />
        <div className="flex items-center gap-2">
          <Skeleton className="h-4 w-14 rounded-full" />
          <Skeleton className="h-4 w-16 rounded-full" />
          <Skeleton className="h-3 w-24" />
        </div>
        <div className="flex gap-1">
          <Skeleton className="h-4 w-10 rounded" />
          <Skeleton className="h-4 w-10 rounded" />
          <Skeleton className="h-4 w-10 rounded" />
        </div>
        <Skeleton className="h-3 w-3/4" />
      </div>
    </div>
  )
}

export function NarrativesSkeleton() {
  return (
    <div className="space-y-4">
      {/* Tab bar skeleton */}
      <div className="flex items-center gap-4 border-b border-border/30 pb-2">
        <Skeleton className="h-5 w-16" />
        <Skeleton className="h-5 w-20" />
        <Skeleton className="h-5 w-28" />
      </div>

      {/* 2x2 card grid skeleton */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {[0, 1, 2, 3].map((index) => (
          <NarrativeCardSkeleton key={index} />
        ))}
      </div>
    </div>
  )
}
