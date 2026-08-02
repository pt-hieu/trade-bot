import { useMemo, useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '../../ui/collapsible'
import { GeopoliticalShockBanner } from '../geopolitical-shock-banner'
import { categorizeArticles, InlineNewsCluster } from './contextual-news'
import type { GeopoliticalShockData } from '../../../types/index'
import type { ArticleSummary, RegimeData, MacroData } from '../../../types/intel'

// ── General news collapsible (Tier 3 — single expandable line) ──────────

function GeneralNewsCollapsible({ articles }: { articles: ArticleSummary[] }) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger className="flex items-center gap-1.5 group cursor-pointer">
        <ChevronRight className="h-3 w-3 text-zinc-500 transition-transform group-data-[state=open]:rotate-90" />
        <span className="text-xs text-zinc-500">
          {articles.length} market article{articles.length !== 1 ? 's' : ''}
        </span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-1.5">
          <InlineNewsCluster articles={articles} />
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

// ── Section ─────────────────────────────────────────────────────────────────

interface IntelligenceSectionProps {
  shock: GeopoliticalShockData | null
  articles: ArticleSummary[]
  regime?: RegimeData | null
  macro?: MacroData | null
  holdingTickers: string[]
  pickTickers: string[]
  watchlistTickers: string[]
}

export function IntelligenceSection({
  shock,
  articles,
  regime,
  macro,
  holdingTickers,
  pickTickers,
  watchlistTickers,
}: IntelligenceSectionProps) {
  const [emptyOpen, setEmptyOpen] = useState(false)

  const { holdingNews, pickNews, watchlistNews, generalNews } = useMemo(
    () => categorizeArticles(articles, holdingTickers, pickTickers, watchlistTickers),
    [articles, holdingTickers, pickTickers, watchlistTickers],
  )

  const hasShock = shock != null
  const hasCategorizedNews = holdingNews.length > 0 || pickNews.length > 0 || watchlistNews.length > 0
  const hasGeneralNews = generalNews.length > 0
  const allNeutral = generalNews.every(
    (article) => article.sentiment_score === null || article.sentiment_score === 0,
  )
  const isEmpty = !hasShock && !hasCategorizedNews && !hasGeneralNews

  if (isEmpty) return null

  // If no catalyst and all news is neutral, compress to a single collapsible line
  if (!hasShock && !hasCategorizedNews && allNeutral) {
    return (
      <Collapsible open={emptyOpen} onOpenChange={setEmptyOpen}>
        <div className="space-y-2">
          <CollapsibleTrigger className="flex items-center gap-1.5 group cursor-pointer">
            <ChevronRight className="h-3 w-3 text-muted-foreground transition-transform group-data-[state=open]:rotate-90" />
            <h3 className="text-xs font-medium tracking-widest text-muted-foreground uppercase">
              Intelligence
            </h3>
            <span className="text-xs text-zinc-500">
              — {generalNews.length} article{generalNews.length !== 1 ? 's' : ''}, all neutral
            </span>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="mt-1">
              <InlineNewsCluster articles={generalNews} />
            </div>
          </CollapsibleContent>
        </div>
      </Collapsible>
    )
  }

  return (
    <div className="space-y-2">
      <h3 className="text-xs font-medium tracking-widest text-muted-foreground uppercase">
        Intelligence
      </h3>

      <div className="rounded-xl border border-border/30 bg-card/20 overflow-hidden">
        {/* Catalyst — top of block, full-width */}
        {hasShock && (
          <div className="border-b border-border/20">
            <GeopoliticalShockBanner
              shock={shock!}
              regime={regime}
              macro={macro}
            />
          </div>
        )}

        {/* News feed — unified row format, categorized by relevance */}
        <div className="p-3 space-y-3">
          {holdingNews.length > 0 && (
            <InlineNewsCluster articles={holdingNews} label="Holdings" tint="holdings" />
          )}
          {pickNews.length > 0 && (
            <InlineNewsCluster articles={pickNews} label="Picks" tint="picks" />
          )}
          {watchlistNews.length > 0 && (
            <InlineNewsCluster articles={watchlistNews} label="Watchlist" tint="watchlist" />
          )}

          {/* General news — collapsed by default */}
          {hasGeneralNews && (
            <GeneralNewsCollapsible articles={generalNews} />
          )}
        </div>
      </div>
    </div>
  )
}
