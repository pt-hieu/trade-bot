import { ExternalLink } from 'lucide-react'
import { cn } from '../../../lib/utils'
import type { ArticleSummary } from '../../../types/intel'
import { sentimentColor } from '../news-section'

// ── Sentiment label (compact for inline row usage) ───────────────────────────

function sentimentLabelShort(score: number | null): string {
  if (score === null || score === 0) return 'Neutral'
  if (score > 0) return 'Pos'
  return 'Neg'
}

// ── Categorization ────────────────────────────────────────────────────────────

export interface CategorizedNews {
  holdingNews: ArticleSummary[]
  pickNews: ArticleSummary[]
  watchlistNews: ArticleSummary[]
  generalNews: ArticleSummary[]
}

export function categorizeArticles(
  articles: ArticleSummary[],
  holdingTickers: string[],
  pickTickers: string[],
  watchlistTickers: string[],
): CategorizedNews {
  const holdingSet = new Set(holdingTickers)
  const pickSet = new Set(pickTickers)
  const watchlistSet = new Set(watchlistTickers)

  const categorized: CategorizedNews = {
    holdingNews: [],
    pickNews: [],
    watchlistNews: [],
    generalNews: [],
  }

  for (const article of articles) {
    const tickers = article.affected_tickers ?? []

    if (tickers.some((ticker) => holdingSet.has(ticker))) {
      categorized.holdingNews.push(article)
    } else if (tickers.some((ticker) => pickSet.has(ticker))) {
      categorized.pickNews.push(article)
    } else if (tickers.some((ticker) => watchlistSet.has(ticker))) {
      categorized.watchlistNews.push(article)
    } else {
      categorized.generalNews.push(article)
    }
  }

  return categorized
}

// ── Inline News Cluster ───────────────────────────────────────────────────────

interface InlineNewsClusterProps {
  articles: ArticleSummary[]
  /** Category label shown above the cluster */
  label?: string
  /** Section color class for the connecting tint on news rows */
  tint?: 'holdings' | 'picks' | 'watchlist'
}

const TINT_CLASS = {
  holdings: 'bg-sky-500/5',
  picks: 'bg-emerald-500/5',
  watchlist: 'bg-amber-500/5',
} as const

const LABEL_DOT = {
  holdings: 'bg-sky-400',
  picks: 'bg-emerald-400',
  watchlist: 'bg-amber-400',
} as const

export function InlineNewsCluster({ articles, label, tint }: InlineNewsClusterProps) {
  if (articles.length === 0) return null

  return (
    <div className="space-y-1">
      {label && (
        <div className="flex items-center gap-1.5 pb-0.5">
          {tint && <span className={cn('h-1.5 w-1.5 rounded-full', LABEL_DOT[tint])} />}
          <span className="text-xs font-medium text-zinc-500">{label}</span>
          <span className="text-xs text-zinc-600">{articles.length}</span>
        </div>
      )}
      <div className="space-y-0.5">
        {articles.map((article, index) => (
          <a
            key={index}
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className={cn(
              'group flex items-center gap-2.5 px-3 py-1.5 rounded-md',
              tint ? TINT_CLASS[tint] : 'bg-muted/20',
              'hover:bg-muted/50 transition-colors duration-150',
              'cursor-pointer',
            )}
          >
            {/* Sentiment pill */}
            <span
              className={cn(
                'shrink-0 text-xs font-medium px-1.5 py-0.5 rounded',
                sentimentColor(article.sentiment_score),
              )}
            >
              {sentimentLabelShort(article.sentiment_score)}
            </span>

            {/* Title */}
            <span className="flex-1 text-xs text-zinc-300 group-hover:text-zinc-100 line-clamp-1 transition-colors min-w-0">
              {article.title}
            </span>

            {/* Ticker badges */}
            {article.affected_tickers?.length > 0 && (
              <div className="flex items-center gap-1 shrink-0">
                {article.affected_tickers.slice(0, 3).map((ticker) => (
                  <span
                    key={ticker}
                    className="text-xs font-mono font-medium px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400"
                  >
                    {ticker}
                  </span>
                ))}
                {article.affected_tickers.length > 3 && (
                  <span className="text-xs font-mono text-zinc-600">
                    +{article.affected_tickers.length - 3}
                  </span>
                )}
              </div>
            )}

            <ExternalLink className="h-3 w-3 text-zinc-700 group-hover:text-zinc-500 transition-colors shrink-0" />
          </a>
        ))}
      </div>
    </div>
  )
}
