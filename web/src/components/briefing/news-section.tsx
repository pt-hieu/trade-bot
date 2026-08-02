import { ExternalLink } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { ArticleSummary } from '../../types/index'

interface NewsSectionProps {
  articles: ArticleSummary[]
}

export function sentimentColor(score: number | null): string {
  if (score === null || score === 0) return 'bg-muted/50 text-muted-foreground'
  if (score > 0) return 'bg-emerald-500/10 text-emerald-400'
  return 'bg-rose-500/10 text-rose-400'
}

export function sentimentLabel(score: number | null): string {
  if (score === null || score === 0) return 'Neutral'
  if (score > 0) return 'Positive'
  return 'Negative'
}

function domainLabel(domain: string | null): string {
  if (!domain) return ''
  return domain.replace('www.', '').split('.')[0]
}

export function NewsSection({ articles }: NewsSectionProps) {
  if (articles.length === 0) return null

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 animate-in fade-in slide-in-from-bottom-2 duration-500" style={{ animationDelay: '240ms' }}>
      {articles.map((article, index) => (
        <a
          key={index}
          href={article.url}
          target="_blank"
          rel="noopener noreferrer"
          className={cn(
            "group relative flex flex-col gap-3 p-4 rounded-lg border border-border/50",
            "bg-card/50 hover:bg-card hover:border-border transition-all duration-200",
            "cursor-pointer",
          )}
        >
          {/* Header: domain + sentiment */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              {article.domain && (
                <span className="text-xs font-mono text-zinc-400 uppercase tracking-wider shrink-0">
                  {domainLabel(article.domain)}
                </span>
              )}
              <span className={cn(
                "text-xs font-medium px-1.5 py-0.5 rounded shrink-0",
                sentimentColor(article.sentiment_score),
              )}>
                {sentimentLabel(article.sentiment_score)}
              </span>
            </div>
            <ExternalLink className="w-3 h-3 text-zinc-600 group-hover:text-muted-foreground transition-colors shrink-0" />
          </div>

          {/* Title */}
          <h3 className="text-sm font-medium leading-snug text-foreground line-clamp-2 group-hover:text-emerald-400 transition-colors">
            {article.title}
          </h3>

          {/* Summary */}
          {article.summary && (
            <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">
              {article.summary}
            </p>
          )}

          {/* Tickers */}
          {article.affected_tickers?.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-auto pt-1">
              {article.affected_tickers.slice(0, 5).map((ticker) => (
                <span
                  key={ticker}
                  className="text-xs font-mono font-medium px-1.5 py-0.5 rounded bg-muted/60 text-zinc-200"
                >
                  {ticker}
                </span>
              ))}
              {article.affected_tickers.length > 5 && (
                <span className="text-xs font-mono text-muted-foreground px-1.5 py-0.5">
                  +{article.affected_tickers.length - 5}
                </span>
              )}
            </div>
          )}
        </a>
      ))}
    </div>
  )
}
