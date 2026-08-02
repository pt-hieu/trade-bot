import { cn } from '../../lib/utils'
import { toTitleCase } from '../../lib/utils'
import { IMPACT_LABELS } from '../catalysts-utils'
import { NARRATIVE_TYPE_LABELS, MATURITY_LABELS, deriveMomentum } from '../narratives/narrative-utils'
import { maturityDotColor, formatNarrativeDateRange, formatCatalystDate } from './newsroom-utils'
import { ScoreIndicator, TickerRow, Dot } from './shared'
import type { Narrative, Catalyst } from '../../types/index'

export type FeedItem =
  | { type: 'theme'; data: Narrative; score: number }
  | { type: 'catalyst'; data: Catalyst; score: number }

const MAX_VISIBLE_TICKERS = 4

/** Themes above this get wide 2-col cards */
export const WIDE_THEME_THRESHOLD = 0.5

interface FeedCardProps {
  item: FeedItem
  index: number
  onSelect: (item: FeedItem) => void
  onTickerClick?: (ticker: string) => void
  highlightedTicker?: string | null
  isSelected?: boolean
}

export function FeedCard({ item, index, onSelect, onTickerClick, highlightedTicker, isSelected }: FeedCardProps) {
  const isTheme = item.type === 'theme'
  const tickers = item.data.affected_tickers ?? []
  const scorePct = Math.round(item.score * 100)
  const isWideTheme = isTheme && item.data.conviction_score >= WIDE_THEME_THRESHOLD

  return (
    <button
      type="button"
      onClick={() => onSelect(item)}
      className={cn(
        'w-full text-left rounded-lg border overflow-hidden flex flex-col justify-start',
        'hover:border-border/60 transition-all duration-200 cursor-pointer',
        'px-3 py-2.5 group',
        'animate-in fade-in slide-in-from-bottom-2 duration-500 fill-mode-backwards',
        isSelected ? 'border-foreground/30 bg-card/80' : 'border-border/40',
        isWideTheme ? 'md:col-span-2 space-y-2' : 'space-y-1.5',
        !isTheme && item.data.status === 'imminent' && 'border-amber-500/30 bg-amber-500/[0.03]',
      )}
      style={{ animationDelay: `${index * 40}ms` }}
    >
      {isWideTheme ? (
        <WideThemeContent narrative={item.data} scorePct={scorePct} tickers={tickers} highlightedTicker={highlightedTicker} onTickerClick={onTickerClick} />
      ) : isTheme ? (
        <CompactThemeContent narrative={item.data} scorePct={scorePct} tickers={tickers} highlightedTicker={highlightedTicker} onTickerClick={onTickerClick} />
      ) : (
        <CatalystCardContent catalyst={item.data} scorePct={scorePct} tickers={tickers} highlightedTicker={highlightedTicker} onTickerClick={onTickerClick} />
      )}
    </button>
  )
}

interface CardContentProps {
  scorePct: number
  tickers: string[]
  highlightedTicker?: string | null
  onTickerClick?: (ticker: string) => void
}

function WideThemeContent({ narrative, scorePct, tickers, highlightedTicker, onTickerClick }: CardContentProps & { narrative: Narrative }) {
  const momentum = deriveMomentum(narrative)
  const visibleTickers = tickers.slice(0, 6)
  const hiddenCount = tickers.length - 6
  const dateRange = formatNarrativeDateRange(narrative)

  return (
    <>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <span className="text-[9px] uppercase tracking-wider font-medium text-blue-400/70">Theme</span>
          <p className="text-sm font-medium text-foreground leading-snug mt-0.5 group-hover:text-foreground/90">{narrative.theme}</p>
        </div>
        <ScoreIndicator score={scorePct} />
      </div>
      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground/60 flex-wrap">
        <span className="text-muted-foreground/80">{NARRATIVE_TYPE_LABELS[narrative.narrative_type]}</span>
        <Dot />
        <span className={cn('h-1.5 w-1.5 rounded-full shrink-0', maturityDotColor(narrative.maturity))} />
        <span>{MATURITY_LABELS[narrative.maturity]}</span>
        <Dot />
        <span>{narrative.article_count} articles</span>
        <Dot />
        <span className="font-mono">{dateRange}</span>
        {momentum !== 'Steady' && (
          <>
            <Dot />
            <span className={momentum === 'Building' ? 'text-emerald-400/70' : 'text-muted-foreground/40'}>{momentum}</span>
          </>
        )}
      </div>
      <div className="flex items-end justify-between gap-4">
        {tickers.length > 0 && (
          <TickerRow tickers={visibleTickers} hiddenCount={hiddenCount} highlightedTicker={highlightedTicker} onTickerClick={onTickerClick} />
        )}
        {narrative.trading_implication && (
          <p className="text-[11px] text-muted-foreground/40 leading-relaxed line-clamp-1 shrink-0 max-w-[45%] text-right">
            {narrative.trading_implication}
          </p>
        )}
      </div>
    </>
  )
}

function CompactThemeContent({ narrative, scorePct, tickers, highlightedTicker, onTickerClick }: CardContentProps & { narrative: Narrative }) {
  const visibleTickers = tickers.slice(0, MAX_VISIBLE_TICKERS)
  const hiddenCount = tickers.length - MAX_VISIBLE_TICKERS
  const dateRange = formatNarrativeDateRange(narrative)

  return (
    <>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <span className="text-[9px] uppercase tracking-wider font-medium text-blue-400/50">Theme</span>
          <p className="text-[13px] font-medium text-foreground leading-snug mt-0.5 line-clamp-2 group-hover:text-foreground/90">{narrative.theme}</p>
        </div>
        <ScoreIndicator score={scorePct} />
      </div>
      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground/60">
        <span className={cn('h-1.5 w-1.5 rounded-full shrink-0', maturityDotColor(narrative.maturity))} />
        <span>{MATURITY_LABELS[narrative.maturity]}</span>
        <Dot />
        <span>{narrative.article_count} articles</span>
        <Dot />
        <span className="font-mono">{dateRange}</span>
      </div>
      {tickers.length > 0 && (
        <TickerRow tickers={visibleTickers} hiddenCount={hiddenCount} highlightedTicker={highlightedTicker} onTickerClick={onTickerClick} />
      )}
    </>
  )
}

function CatalystCardContent({ catalyst, scorePct, tickers, highlightedTicker, onTickerClick }: CardContentProps & { catalyst: Catalyst }) {
  const visibleTickers = tickers.slice(0, MAX_VISIBLE_TICKERS)
  const hiddenCount = tickers.length - MAX_VISIBLE_TICKERS
  const dateDisplay = formatCatalystDate(catalyst)

  return (
    <>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <span className={cn(
            'text-[9px] uppercase tracking-wider font-medium',
            catalyst.status === 'imminent' ? 'text-amber-400/80' : 'text-amber-400/60'
          )}>
            {catalyst.status === 'imminent' ? 'Imminent Catalyst' : 'Catalyst'}
          </span>
          <p className="text-[13px] font-medium text-foreground leading-snug mt-0.5 line-clamp-2 group-hover:text-foreground/90">{catalyst.event}</p>
        </div>
        <ScoreIndicator score={scorePct} />
      </div>
      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground/60">
        <span className="font-mono text-muted-foreground/80">{dateDisplay}</span>
        <Dot />
        <span>{toTitleCase(catalyst.confidence)}</span>
        <Dot />
        <span>{IMPACT_LABELS[catalyst.impact] ?? catalyst.impact}</span>
      </div>
      {tickers.length > 0 && (
        <TickerRow tickers={visibleTickers} hiddenCount={hiddenCount} highlightedTicker={highlightedTicker} onTickerClick={onTickerClick} />
      )}
      {catalyst.notes && (
        <p className="text-[11px] text-muted-foreground/40 leading-relaxed line-clamp-1">{catalyst.notes}</p>
      )}
    </>
  )
}
