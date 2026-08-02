import { Link } from '@tanstack/react-router'
import { Card } from '../ui/card'
import { Skeleton } from '../ui/skeleton'
import { cn } from '../../lib/utils'
import type { ArticleSummary } from '../../types/index'

function sentimentDot(score: number | null): string {
  if (score == null) return 'bg-muted-foreground/30'
  if (score > 0.2) return 'bg-emerald-500'
  if (score < -0.2) return 'bg-rose-500'
  return 'bg-muted-foreground/30'
}

interface NewsMiniProps {
  articles: ArticleSummary[] | undefined
  isLoading: boolean
}

export function NewsMini({ articles, isLoading }: NewsMiniProps) {
  const sorted = articles
    ? [...articles]
        .sort((a, b) => Math.abs(b.sentiment_score ?? 0) - Math.abs(a.sentiment_score ?? 0))
        .slice(0, 3)
    : []

  return (
    <Card className="border-border/50 py-0 gap-0 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/30">
        <h3 className="text-[10px] font-medium tracking-widest text-muted-foreground uppercase">
          News
        </h3>
        <Link
          to="/briefing" search={{} as any}
          className="text-[10px] text-muted-foreground hover:text-foreground transition-colors"
        >
          Briefing →
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

        {!isLoading && sorted.length === 0 && (
          <p className="text-xs text-muted-foreground">
            No articles yet. Morning scan populates news.
          </p>
        )}

        {!isLoading && sorted.map((a, i) => {
          const text = a.summary || a.title || ''
          return (
            <div key={i} className="flex items-start gap-2 min-w-0">
              <span
                className={cn('h-1.5 w-1.5 rounded-full shrink-0 mt-1.5', sentimentDot(a.sentiment_score))}
              />
              <div className="min-w-0 flex-1">
                <a
                  href={a.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block text-[11px] text-foreground/90 hover:text-foreground transition-colors line-clamp-2 leading-[1.4]"
                >
                  {text}
                </a>
                {(a.affected_tickers ?? []).length > 0 && (
                  <div className="flex gap-1 mt-0.5">
                    {a.affected_tickers.slice(0, 3).map((t) => (
                      <span key={t} className="font-mono text-[9px] text-muted-foreground/70 bg-muted/30 px-1 rounded">
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}
