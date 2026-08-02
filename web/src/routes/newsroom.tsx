import { createFileRoute, useSearch, useNavigate } from '@tanstack/react-router'
import { useState, useMemo, useCallback } from 'react'
import { Newspaper, DollarSign, ChevronDown, ArrowUpDown } from 'lucide-react'
import { Badge } from '../components/ui/badge'
import { EmptyState } from '../components/ui/empty-state'
import { ErrorState } from '../components/ui/error-state'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '../components/ui/collapsible'
import { cn } from '../lib/utils'
import { toDateStr } from '../lib/date'
import { useNarratives } from '../hooks/use-narratives'
import { useCatalysts, useCapitalEvents } from '../hooks/use-catalysts'
import { NarrativeFilters } from '../components/narratives/narrative-filters'
import { NarrativesSkeleton } from '../components/narratives/narrative-skeleton'
import { FeedCard } from '../components/newsroom/feed-card'
import { FeedDetailPanel } from '../components/newsroom/feed-detail-panel'
import { SpotlightStrip } from '../components/newsroom/spotlight-strip'
import { scoreCatalyst } from '../components/newsroom/newsroom-utils'
import { impactBadge, EVENT_TYPE_LABELS, IMPACT_LABELS } from '../components/catalysts-utils'
import type { Narrative, Catalyst, CapitalEvent } from '../types/index'
import type { FeedItem } from '../components/newsroom/feed-card'

export const Route = createFileRoute('/newsroom')({
  validateSearch: (search: Record<string, unknown>) => ({
    ticker: (search.ticker as string) ?? undefined,
  }),
  component: NewsroomPage,
  ssr: false,
})

type SortMode = 'score' | 'recent'

function feedItemDate(item: FeedItem): string {
  const raw = item.type === 'theme'
    ? item.data.last_seen
    : (item.data.expected_date ?? item.data.updated_at ?? item.data.created_at)
  return toDateStr(raw)
}

function NewsroomPage() {
  const search = useSearch({ from: '/newsroom' })
  const navigate = useNavigate()
  const routeTickerFilter = search.ticker

  const [tickerFilter, setTickerFilter] = useState('')
  const [maturity, setMaturity] = useState('all')
  const [selectedItem, setSelectedItem] = useState<FeedItem | null>(null)
  const [sortMode, setSortMode] = useState<SortMode>('score')
  const [capitalEventsOpen, setCapitalEventsOpen] = useState(false)

  const effectiveTickerFilter = routeTickerFilter || tickerFilter || undefined

  const { data: rawNarratives, isLoading: narrativesLoading, error: narrativesError, refetch: refetchNarratives } =
    useNarratives({ status: 'active', ticker: routeTickerFilter })
  const { data: rawCatalysts, isLoading: catalystsLoading, error: catalystsError, refetch: refetchCatalysts } =
    useCatalysts()
  const { data: capitalEvents, isLoading: capitalEventsLoading } =
    useCapitalEvents()

  const narratives = (rawNarratives ?? []) as Narrative[]
  const catalysts = (rawCatalysts ?? []) as Catalyst[]
  const events = (capitalEvents ?? []) as CapitalEvent[]

  const filteredNarratives = useMemo(() => {
    let result = narratives
    if (maturity !== 'all') result = result.filter((narrative) => narrative.maturity === maturity)
    if (!routeTickerFilter && tickerFilter) {
      const upperFilter = tickerFilter.toUpperCase()
      result = result.filter((narrative) =>
        narrative.affected_tickers?.some((ticker) => ticker.toUpperCase().includes(upperFilter))
      )
    }
    return result
  }, [narratives, maturity, tickerFilter, routeTickerFilter])

  const activeCatalysts = useMemo(() =>
    catalysts.filter((catalyst) => catalyst.status !== 'resolved' && catalyst.status !== 'expired'),
    [catalysts]
  )

  const filteredCatalysts = useMemo(() => {
    if (!effectiveTickerFilter) return activeCatalysts
    return activeCatalysts.filter((catalyst) =>
      catalyst.affected_tickers?.some((ticker) => ticker.toUpperCase().includes(effectiveTickerFilter.toUpperCase()))
    )
  }, [activeCatalysts, effectiveTickerFilter])

  const feedItems = useMemo<FeedItem[]>(() => {
    const all: FeedItem[] = [
      ...filteredNarratives.map((narrative) => ({ type: 'theme' as const, data: narrative, score: narrative.conviction_score })),
      ...filteredCatalysts.map((catalyst) => ({ type: 'catalyst' as const, data: catalyst, score: scoreCatalyst(catalyst) })),
    ]
    return sortMode === 'score'
      ? all.sort((itemA, itemB) => itemB.score - itemA.score)
      : all.sort((itemA, itemB) => feedItemDate(itemB).localeCompare(feedItemDate(itemA)))
  }, [filteredNarratives, filteredCatalysts, sortMode])

  const spotlightThemes = useMemo(() =>
    [...filteredNarratives].sort((narrativeA, narrativeB) => narrativeB.conviction_score - narrativeA.conviction_score).slice(0, 3),
    [filteredNarratives]
  )

  const imminentCatalysts = useMemo(() => {
    const sevenDays = new Date(Date.now() + 7 * 86_400_000)
    return activeCatalysts.filter((catalyst) => {
      if (catalyst.status === 'imminent') return true
      const expectedDate = catalyst.expected_date ? new Date(catalyst.expected_date) : null
      return expectedDate !== null && expectedDate <= sevenDays
    }).slice(0, 3)
  }, [activeCatalysts])

  const pendingCapitalEvents = useMemo(() => {
    let result = events.filter((event) => event.status === 'pending')
    if (effectiveTickerFilter) {
      result = result.filter((event) => event.ticker.toUpperCase().includes(effectiveTickerFilter.toUpperCase()))
    }
    return result.sort((eventA, eventB) => eventA.expected_date.localeCompare(eventB.expected_date))
  }, [events, effectiveTickerFilter])

  const handleSelectConnected = useCallback((item: FeedItem) => setSelectedItem(item), [])
  const handleClosePanel = useCallback(() => setSelectedItem(null), [])
  const handleTickerClick = useCallback((ticker: string) => { setTickerFilter(ticker); setSelectedItem(null) }, [])

  const isLoading = narrativesLoading || catalystsLoading
  const hasError = narrativesError || catalystsError

  return (
    <>
      <main className="min-h-[calc(100dvh-77px)] p-6 max-w-7xl mx-auto space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <h1 className="text-xl font-semibold tracking-tight">Newsroom</h1>
          <NarrativeFilters
            tickerFilter={tickerFilter}
            onTickerFilterChange={setTickerFilter}
            maturity={maturity}
            onMaturityChange={setMaturity}
            routeTickerFilter={routeTickerFilter}
            onClearRouteTickerFilter={() => navigate({ to: '/newsroom', search: {} as any })}
          />
        </div>

        {isLoading && <NarrativesSkeleton />}
        {!isLoading && hasError && (
          <ErrorState description="Could not load market intelligence data." retry={() => { refetchNarratives(); refetchCatalysts() }} />
        )}

        {!isLoading && !hasError && (
          <>
            <SpotlightStrip themes={spotlightThemes} catalysts={imminentCatalysts} onSelect={setSelectedItem} />

            <div className="flex items-center justify-between border-b border-dashed border-border/20 pb-2">
              <div className="flex items-center gap-3 text-[10px] text-muted-foreground/50">
                <span><span className="font-mono text-foreground/70">{filteredNarratives.length}</span> themes</span>
                <span><span className="font-mono text-foreground/70">{filteredCatalysts.length}</span> catalysts</span>
                {imminentCatalysts.length > 0 && (
                  <span><span className="font-mono text-amber-400">{imminentCatalysts.length}</span> imminent</span>
                )}
              </div>
              <button
                type="button"
                onClick={() => setSortMode(sortMode === 'score' ? 'recent' : 'score')}
                className="flex items-center gap-1 text-[10px] text-muted-foreground/50 hover:text-foreground transition-colors cursor-pointer"
              >
                <ArrowUpDown className="h-3 w-3" />
                <span>{sortMode === 'score' ? 'By importance' : 'By recency'}</span>
              </button>
            </div>

            {feedItems.length === 0 ? (
              <EmptyState icon={Newspaper} title="No intelligence" description="No themes or catalysts match current filters." />
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {feedItems.map((item, index) => (
                  <FeedCard
                    key={item.type === 'theme' ? `t-${item.data.id}` : `c-${item.data.id}`}
                    item={item}
                    index={index}
                    onSelect={setSelectedItem}
                    onTickerClick={handleTickerClick}
                    highlightedTicker={tickerFilter || null}
                    isSelected={selectedItem?.type === item.type && selectedItem?.data.id === item.data.id}
                  />
                ))}
              </div>
            )}

            {!capitalEventsLoading && pendingCapitalEvents.length > 0 && (
              <Collapsible open={capitalEventsOpen} onOpenChange={setCapitalEventsOpen}>
                <CollapsibleTrigger className="flex items-center gap-2 w-full cursor-pointer">
                  <DollarSign className="h-3 w-3 text-muted-foreground/40" />
                  <span className="font-mono text-[11px] tracking-wider text-muted-foreground/50 uppercase">Capital Events</span>
                  <span className="font-mono text-[11px] text-muted-foreground/40">{pendingCapitalEvents.length}</span>
                  <div className="flex-1 border-t border-dotted border-border/20" />
                  <ChevronDown className={cn('h-3 w-3 text-muted-foreground/40 transition-transform', capitalEventsOpen && 'rotate-180')} />
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <div className="mt-3 rounded-lg border border-border/40 overflow-hidden">
                    <div className="grid grid-cols-[80px_100px_1fr_100px_100px] gap-3 px-3 py-2 bg-muted/10 text-[10px] text-muted-foreground/50 border-b border-border/30">
                      <span>Ticker</span><span>Type</span><span>Description</span><span>Impact</span><span className="text-right">Expected</span>
                    </div>
                    {pendingCapitalEvents.map((event) => (
                      <div key={event.id} className="grid grid-cols-[80px_100px_1fr_100px_100px] gap-3 px-3 py-2 border-t border-border/20 hover:bg-card/60 transition-colors text-xs items-center">
                        <span className="font-mono font-medium text-foreground">{event.ticker}</span>
                        <Badge variant="outline" className={cn('text-[9px] py-0 px-1 w-fit', impactBadge(event.impact))}>
                          {EVENT_TYPE_LABELS[event.event_type] ?? event.event_type}
                        </Badge>
                        <span className="text-muted-foreground/70 truncate min-w-0">{event.description}</span>
                        <span className="text-[10px] text-muted-foreground/50">{IMPACT_LABELS[event.impact] ?? event.impact}</span>
                        <span className="font-mono text-[10px] text-muted-foreground/50 text-right">{event.expected_date}</span>
                      </div>
                    ))}
                  </div>
                </CollapsibleContent>
              </Collapsible>
            )}
          </>
        )}
      </main>

      <FeedDetailPanel
        item={selectedItem}
        onClose={handleClosePanel}
        allNarratives={narratives}
        allCatalysts={activeCatalysts}
        onSelectConnected={handleSelectConnected}
        onTickerClick={handleTickerClick}
      />
      {selectedItem && <div className="fixed inset-0 z-40 bg-black/20 lg:hidden" onClick={handleClosePanel} />}
    </>
  )
}
