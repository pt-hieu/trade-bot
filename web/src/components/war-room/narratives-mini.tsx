import { Link } from '@tanstack/react-router'
import { Card } from '../ui/card'
import { Skeleton } from '../ui/skeleton'
import { cn } from '../../lib/utils'
import { useNarratives } from '../../hooks/use-narratives'
import { convictionDotColor, deriveMomentum, momentumBadgeClass } from '../narratives/narrative-utils'

export function NarrativesMini() {
  const { data: narratives, isLoading } = useNarratives({ status: 'active' })
  const top3 = (narratives ?? []).slice(0, 3)

  return (
    <Card className="border-border/50 py-0 gap-0 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/30">
        <h3 className="text-[10px] font-medium tracking-widest text-muted-foreground uppercase">
          Narratives
        </h3>
        <Link
          to="/newsroom" search={{} as any}
          className="text-[10px] text-muted-foreground hover:text-foreground transition-colors"
        >
          Newsroom →
        </Link>
      </div>

      <div className="px-4 py-3 space-y-2.5">
        {isLoading && (
          Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex items-center gap-2">
              <Skeleton className="h-2 w-2 rounded-full shrink-0" />
              <Skeleton className="h-3 flex-1" />
            </div>
          ))
        )}

        {!isLoading && top3.length === 0 && (
          <p className="text-xs text-muted-foreground">No active narratives</p>
        )}

        {!isLoading && top3.map((narrative: any) => {
          const momentum = deriveMomentum(narrative)
          const momentumTextClass = momentumBadgeClass(momentum).split(' ').find((c) => c.startsWith('text-')) ?? 'text-muted-foreground'
          return (
            <div key={narrative.id} className="flex items-start gap-2 min-w-0">
              <span
                className={cn('h-1.5 w-1.5 rounded-full shrink-0 mt-1', convictionDotColor(narrative.conviction_score))}
              />
              <div className="min-w-0 flex-1">
                <p className="text-[11px] text-foreground/90 line-clamp-1 leading-snug">{narrative.theme}</p>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className={cn('text-[9px]', momentumTextClass)}>{momentum}</span>
                  {(narrative.affected_tickers ?? []).length > 0 && (
                    <div className="flex gap-1">
                      {narrative.affected_tickers.slice(0, 3).map((t: any) => (
                        <span key={t} className="font-mono text-[9px] text-muted-foreground/70 bg-muted/30 px-1 rounded">
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}
