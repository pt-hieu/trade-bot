import { useEffect, useMemo } from 'react'
import { X, Newspaper, Clock, BarChart3, Link2 } from 'lucide-react'
import { cn } from '../../lib/utils'
import { toTitleCase } from '../../lib/utils'
import { IMPACT_LABELS } from '../catalysts-utils'
import { deriveMomentum, NARRATIVE_TYPE_LABELS, MATURITY_LABELS } from '../narratives/narrative-utils'
import { scoreBarColor, scoreTextColor, formatNarrativeDateRange, formatCatalystDate, scoreCatalyst } from './newsroom-utils'
import { Dot, TickerChip, Section, StatBlock } from './shared'
import { TimelineWithMarkers, PhasesTimeline } from './timeline'
import type { Narrative, Catalyst } from '../../types/index'
import type { FeedItem } from './feed-card'

interface FeedDetailPanelProps {
  item: FeedItem | null
  onClose: () => void
  allNarratives: Narrative[]
  allCatalysts: Catalyst[]
  onSelectConnected: (item: FeedItem) => void
  onTickerClick?: (ticker: string) => void
}

function findConnectedCatalysts(narrative: Narrative, catalysts: Catalyst[]): Catalyst[] {
  const tickerSet = new Set(narrative.affected_tickers ?? [])
  if (tickerSet.size === 0) return []
  return catalysts.filter((catalyst) =>
    catalyst.status !== 'resolved' && catalyst.status !== 'expired' &&
    (catalyst.affected_tickers ?? []).some((ticker) => tickerSet.has(ticker))
  )
}

function findConnectedNarratives(catalyst: Catalyst, narratives: Narrative[]): Narrative[] {
  const tickerSet = new Set(catalyst.affected_tickers ?? [])
  if (tickerSet.size === 0) return []
  return narratives.filter((narrative) =>
    (narrative.affected_tickers ?? []).some((ticker) => tickerSet.has(ticker))
  )
}

export function FeedDetailPanel({ item, onClose, allNarratives, allCatalysts, onSelectConnected, onTickerClick }: FeedDetailPanelProps) {
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    if (item) document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [item, onClose])

  const connectedCatalysts = useMemo(() =>
    item?.type === 'theme' ? findConnectedCatalysts(item.data, allCatalysts) : [],
    [item, allCatalysts]
  )

  const connectedNarratives = useMemo(() =>
    item?.type === 'catalyst' ? findConnectedNarratives(item.data, allNarratives) : [],
    [item, allNarratives]
  )

  return (
    <div className={cn(
      'fixed top-0 right-0 h-full w-[420px] max-w-[90vw] z-50',
      'bg-background border-l border-border/50',
      'transform transition-transform duration-300 ease-out',
      'shadow-2xl shadow-black/20',
      item ? 'translate-x-0' : 'translate-x-full'
    )}>
      {item && (
        <div className="h-full flex flex-col">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border/30 shrink-0">
            <span className={cn(
              'text-[9px] uppercase tracking-wider font-medium',
              item.type === 'theme' ? 'text-blue-400/70' : 'text-amber-400/70'
            )}>
              {item.type === 'theme' ? 'Theme' : 'Catalyst'}
            </span>
            <button
              type="button"
              onClick={onClose}
              className="h-6 w-6 rounded-md flex items-center justify-center hover:bg-muted/30 transition-colors cursor-pointer text-muted-foreground/60 hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
            {item.type === 'theme' ? (
              <ThemeDetail
                narrative={item.data}
                connectedCatalysts={connectedCatalysts}
                onSelectCatalyst={(catalyst) => onSelectConnected({ type: 'catalyst', data: catalyst, score: scoreCatalyst(catalyst) })}
                onTickerClick={onTickerClick}
              />
            ) : (
              <CatalystDetail
                catalyst={item.data}
                connectedNarratives={connectedNarratives}
                onSelectNarrative={(narrative) => onSelectConnected({ type: 'theme', data: narrative, score: narrative.conviction_score })}
                onTickerClick={onTickerClick}
              />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function ThemeDetail({ narrative, connectedCatalysts, onSelectCatalyst, onTickerClick }: {
  narrative: Narrative; connectedCatalysts: Catalyst[]; onSelectCatalyst: (catalyst: Catalyst) => void; onTickerClick?: (ticker: string) => void
}) {
  const momentum = deriveMomentum(narrative)
  const updates = narrative.updates ?? []
  const tickers = narrative.affected_tickers ?? []
  const convictionPct = Math.round(narrative.conviction_score * 100)
  const dateRange = formatNarrativeDateRange(narrative)

  return (
    <>
      <div className="flex items-start gap-3">
        <h2 className="text-base font-semibold leading-snug flex-1">{narrative.theme}</h2>
        <div className="flex flex-col items-end shrink-0 gap-1">
          <span className={cn('font-mono text-sm font-semibold tabular-nums', scoreTextColor(narrative.conviction_score))}>
            {convictionPct}
          </span>
          <div className="w-12 h-1 rounded-full bg-muted/30 overflow-hidden">
            <div className={cn('h-full rounded-full', scoreBarColor(narrative.conviction_score))} style={{ width: `${convictionPct}%` }} />
          </div>
        </div>
      </div>
      <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground/60 flex-wrap">
        <span className="text-muted-foreground/80">{NARRATIVE_TYPE_LABELS[narrative.narrative_type]}</span>
        <Dot /><span>{MATURITY_LABELS[narrative.maturity]}</span>
        <Dot /><span>{momentum}</span>
        <Dot /><span>{narrative.article_count} articles</span>
        <Dot /><span className="font-mono">{dateRange}</span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <StatBlock icon={Newspaper} label="Articles" value={String(narrative.article_count)} />
        <StatBlock icon={BarChart3} label="Sources" value={String(narrative.source_count)} />
        <StatBlock icon={Clock} label="Span" value={dateRange} />
      </div>
      {tickers.length > 0 && (
        <Section label="Affected tickers">
          <div className="flex gap-1.5 flex-wrap">
            {tickers.map((ticker) => <TickerChip key={ticker} ticker={ticker} onClick={onTickerClick} />)}
          </div>
        </Section>
      )}
      {narrative.trading_implication && (
        <Section label="Trading implication">
          <p className="text-[13px] text-foreground/80 leading-relaxed">{narrative.trading_implication}</p>
        </Section>
      )}
      {narrative.summary && (
        <Section label="Summary">
          <p className="text-[13px] text-foreground/70 leading-relaxed">{narrative.summary}</p>
        </Section>
      )}
      {connectedCatalysts.length > 0 && (
        <Section label={`Connected catalysts (${connectedCatalysts.length})`} icon={<Link2 className="h-3 w-3 text-amber-400/60" />}>
          <div className="space-y-1.5">
            {connectedCatalysts.map((catalyst) => (
              <ConnectedCard key={catalyst.id} type="catalyst" title={catalyst.event} meta={`${formatCatalystDate(catalyst)} · ${IMPACT_LABELS[catalyst.impact] ?? catalyst.impact}`} badge={catalyst.status === 'imminent' ? 'Imminent' : undefined} onClick={() => onSelectCatalyst(catalyst)} />
            ))}
          </div>
        </Section>
      )}
      {updates.length > 0 && (
        <Section label={`Timeline (${updates.length})`}>
          <TimelineWithMarkers updates={updates} connectedCatalysts={connectedCatalysts} />
        </Section>
      )}
    </>
  )
}

function CatalystDetail({ catalyst, connectedNarratives, onSelectNarrative, onTickerClick }: {
  catalyst: Catalyst; connectedNarratives: Narrative[]; onSelectNarrative: (narrative: Narrative) => void; onTickerClick?: (ticker: string) => void
}) {
  const tickers = catalyst.affected_tickers ?? []
  const dateDisplay = formatCatalystDate(catalyst)

  return (
    <>
      <h2 className="text-base font-semibold leading-snug">{catalyst.event}</h2>
      <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground/60 flex-wrap">
        <span className="font-mono text-muted-foreground/80">{dateDisplay}</span>
        <Dot /><span>{toTitleCase(catalyst.confidence)} confidence</span>
        <Dot /><span>{IMPACT_LABELS[catalyst.impact] ?? catalyst.impact} impact</span>
        {catalyst.status === 'imminent' && (<><Dot /><span className="text-amber-400/80 font-medium">Imminent</span></>)}
      </div>
      {tickers.length > 0 && (
        <Section label="Affected tickers">
          <div className="flex gap-1.5 flex-wrap">
            {tickers.map((ticker) => <TickerChip key={ticker} ticker={ticker} onClick={onTickerClick} />)}
          </div>
        </Section>
      )}
      {catalyst.notes && (
        <Section label="Notes">
          <p className="text-[13px] text-foreground/80 leading-relaxed">{catalyst.notes}</p>
        </Section>
      )}
      {catalyst.phases && Object.keys(catalyst.phases).length > 0 && (
        <Section label="Phases">
          <PhasesTimeline phases={catalyst.phases} />
        </Section>
      )}
      {connectedNarratives.length > 0 && (
        <Section label={`Connected themes (${connectedNarratives.length})`} icon={<Link2 className="h-3 w-3 text-blue-400/60" />}>
          <div className="space-y-1.5">
            {connectedNarratives.map((narrative) => (
              <ConnectedCard key={narrative.id} type="theme" title={narrative.theme} meta={`${MATURITY_LABELS[narrative.maturity]} · ${narrative.article_count} articles`} score={Math.round(narrative.conviction_score * 100)} onClick={() => onSelectNarrative(narrative)} />
            ))}
          </div>
        </Section>
      )}
    </>
  )
}

function ConnectedCard({ type, title, meta, badge, score, onClick }: {
  type: 'theme' | 'catalyst'; title: string; meta: string; badge?: string; score?: number; onClick: () => void
}) {
  return (
    <button type="button" onClick={onClick} className="w-full text-left rounded-md border border-border/30 px-2.5 py-2 hover:bg-muted/20 transition-colors cursor-pointer">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className={cn('text-[9px] uppercase tracking-wider font-medium', type === 'theme' ? 'text-blue-400/60' : 'text-amber-400/60')}>
            {type === 'theme' ? 'Theme' : 'Catalyst'}
          </span>
          {badge && <span className="text-[9px] text-amber-400/80 font-medium">{badge}</span>}
        </div>
        {score !== undefined && (
          <span className={cn('font-mono text-[10px] tabular-nums', scoreTextColor(score / 100))}>{score}</span>
        )}
      </div>
      <p className="text-[12px] text-foreground/80 leading-snug mt-0.5">{title}</p>
      <span className="text-[10px] text-muted-foreground/50 mt-0.5 block">{meta}</span>
    </button>
  )
}
