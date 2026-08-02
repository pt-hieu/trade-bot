import { useMemo } from 'react'
import { Skeleton } from '../../ui/skeleton'
import { RegimeStrip } from '../regime-strip'
import { HoldingsCards } from './holdings-cards'
import { TopPicksCards } from './top-picks-cards'
import { WatchlistChanges } from './watchlist-changes'
import { CollapsibleSection } from './collapsible-section'
import { VerdictSection } from './verdict-section'
import { IntelligenceSection } from './intelligence-section'
import { MarketContextSection } from './market-context-section'
import { deriveVerdict, computeProximity } from './derive-verdict'
import type { DailyIntel, RecommendationsData } from '../../../types/intel'

// ── Known sections ──────────────────────────────────────────────────────────

const KNOWN_SECTIONS = new Set(['MY_HOLDINGS', 'TOP_PICKS', 'LONG_TERM', 'SKIP_THESE'])

// ── Props ───────────────────────────────────────────────────────────────────

interface MorningNarrativeProps {
  intel: DailyIntel | null
  recs: RecommendationsData | null
  recsLoading?: boolean
}

export function MorningNarrative({ intel, recs, recsLoading }: MorningNarrativeProps) {
  // ── Recommendation grouping ─────────────────────────────────────────────
  const { holdings, picks, watchlist, skipped, other } = useMemo(() => {
    const allRecs = recs?.recommendations ?? []
    return {
      holdings: allRecs.filter((rec) => rec.section === 'MY_HOLDINGS'),
      picks: allRecs.filter((rec) => rec.section === 'TOP_PICKS'),
      watchlist: allRecs.filter((rec) => rec.section === 'LONG_TERM'),
      skipped: allRecs.filter((rec) => rec.section === 'SKIP_THESE'),
      other: allRecs.filter((rec) => !rec.section || !KNOWN_SECTIONS.has(rec.section)),
    }
  }, [recs])

  // ── Verdict ─────────────────────────────────────────────────────────────
  const verdictData = useMemo(() => deriveVerdict(recs), [recs])

  // ── Proximity (for watchlist zones) ─────────────────────────────────────
  const proximityData = useMemo(() => computeProximity(watchlist), [watchlist])
  const closestMiss = useMemo(
    () => proximityData.find((item) => item.distancePct !== Infinity) ?? null,
    [proximityData],
  )

  // ── Portfolio tickers (for flow flagging + news categorization) ─────────
  const portfolioTickers = useMemo(() => {
    const tickers = new Set<string>()
    for (const rec of [...holdings, ...picks, ...watchlist]) tickers.add(rec.ticker)
    return tickers
  }, [holdings, picks, watchlist])

  const tickerArrays = useMemo(() => ({
    holdingTickers: holdings.map((rec) => rec.ticker),
    pickTickers: picks.map((rec) => rec.ticker),
    watchlistTickers: watchlist.map((rec) => rec.ticker),
  }), [holdings, picks, watchlist])

  // ── Render: 3-tier density ───────────────────────────────────────────
  return (
    <div className="space-y-6">
      {/* ── Tier 1: First viewport — glance-and-act ──────────────────── */}
      <div className="space-y-3">
        {intel?.regime && <RegimeStrip regime={intel.regime} />}

        {!recsLoading && <VerdictSection verdict={verdictData} />}

        {recsLoading && (
          <div className="space-y-2">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        )}

        {holdings.length > 0 && (
          <div className="space-y-1.5">
            <h3 className="text-xs font-medium tracking-widest text-zinc-500 uppercase">
              Holdings
            </h3>
            <HoldingsCards recs={holdings} />
          </div>
        )}
      </div>

      {/* ── Tier 2: Scroll continuation — narrative arc ──────────────── */}
      <div className="space-y-5">
        {!recsLoading && (
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <h3 className="text-xs font-medium tracking-widest text-muted-foreground uppercase">
                Top Picks
              </h3>
              {skipped.length > 0 && (
                <CollapsibleSection label="skipped" recs={skipped} section="SKIP_THESE" />
              )}
              {other.length > 0 && (
                <CollapsibleSection label="other tickers" recs={other} section="OTHER" />
              )}
            </div>
            <TopPicksCards recs={picks} closestMiss={closestMiss} />
          </div>
        )}

        <IntelligenceSection
          shock={intel?.geopolitical_shock ?? null}
          articles={intel?.articles ?? []}
          regime={intel?.regime}
          macro={intel?.macro}
          holdingTickers={tickerArrays.holdingTickers}
          pickTickers={tickerArrays.pickTickers}
          watchlistTickers={tickerArrays.watchlistTickers}
        />

        {watchlist.length > 0 && (
          <WatchlistChanges recs={watchlist} proximityData={proximityData} />
        )}
      </div>

      {/* ── Tier 3: Collapsed/deferred — reference lookup ────────────── */}
      <div className="space-y-3">
        <MarketContextSection
          macro={intel?.macro ?? null}
          foreignFlow={intel?.foreign_flow ?? null}
          rotation={intel?.rotation ?? null}
          portfolioTickers={portfolioTickers}
        />
      </div>
    </div>
  )
}
