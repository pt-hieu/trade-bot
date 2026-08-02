import { useState, useMemo, Fragment } from 'react'
import {
  useUnifiedWatchlist, useEditWatchlistItem,
  useRemoveFromWatchlist, useUpdateRsi,
} from '../hooks/use-watchlist'
import {
  Table, TableHeader, TableBody, TableHead, TableRow, TableCell,
} from './ui/table'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { Spinner } from './ui/spinner'
import { EmptyState } from './ui/empty-state'
import { ErrorState } from './ui/error-state'
import { ConfirmDialog } from './ui/confirm-dialog'
import { ColumnInfo } from './ui/column-info'
import { WatchlistDialog } from './watchlist-dialog'
import { WatchlistEditDialog } from './watchlist-edit-dialog'
import { UnifiedRow } from './watchlist-unified-row'
import { WatchlistDetailPanel } from './watchlist-detail-panel'
import { useSparklineData } from '../hooks/use-sparkline-data'
import { List, Plus, ChevronRight } from 'lucide-react'
import { cn } from '../lib/utils'
import { compute30dChange } from '../lib/watchlist-utils'
import { READINESS_CONFIG, HOT_URGENCY_THRESHOLD } from '../lib/watchlist-merge'
import type { UnifiedWatchlistItem, ReadinessTier } from '../lib/watchlist-merge'

type PlanFilter = 'all' | 'swing' | 'longterm'

export function WatchlistSection({ addTicker }: { addTicker?: string }) {
  const unified = useUnifiedWatchlist()
  const editMutation = useEditWatchlistItem()
  const removeMutation = useRemoveFromWatchlist()
  const updateRsiMutation = useUpdateRsi()

  const [planFilter, setPlanFilter] = useState<PlanFilter>('all')
  const [addDialogOpen, setAddDialogOpen] = useState(!!addTicker)
  const [editItem, setEditItem] = useState<UnifiedWatchlistItem | null>(null)
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null)
  const [expandedOverflows, setExpandedOverflows] = useState<Set<ReadinessTier>>(new Set())
  const [confirmRemove, setConfirmRemove] = useState<{
    ticker: string; type: 'swing' | 'longterm'
  } | null>(null)

  const toggleOverflow = (tier: ReadinessTier) => {
    setExpandedOverflows((previous) => {
      const next = new Set(previous)
      if (next.has(tier)) next.delete(tier)
      else next.add(tier)
      return next
    })
  }

  const filteredGroups = useMemo(() => {
    if (!unified.grouped) return undefined
    if (planFilter === 'all') return unified.grouped
    return unified.grouped
      .map((group) => ({
        ...group,
        items: group.items.filter((item) => item.plans.includes(planFilter)),
      }))
      .filter((group) => group.tier === 'near_entry' || group.items.length > 0)
  }, [unified.grouped, planFilter])

  // On-demand sparklines for expanded overflow/watching tickers
  const overflowTickers = useMemo(() => {
    if (!filteredGroups) return []
    return filteredGroups.flatMap((group) => {
      if (!expandedOverflows.has(group.tier)) return []
      if (group.tier === 'watching') return group.items.map((item) => item.ticker)
      if (group.tier === 'setting_up') {
        return group.items.filter((item) => item.urgencyScore < HOT_URGENCY_THRESHOLD).map((item) => item.ticker)
      }
      return []
    })
  }, [filteredGroups, expandedOverflows])

  const { data: overflowSparklines, isLoading: overflowSparklinesLoading } = useSparklineData(overflowTickers)

  const mergedSparklines = useMemo(() => {
    if (!unified.sparklines && !overflowSparklines) return undefined
    return { ...unified.sparklines, ...overflowSparklines }
  }, [unified.sparklines, overflowSparklines])

  const totalCount = unified.items?.length ?? 0
  const nearEntryCount = useMemo(
    () => unified.items?.filter((item) => item.readiness === 'near_entry').length ?? 0,
    [unified.items],
  )

  const handleRemove = (item: UnifiedWatchlistItem) => {
    const removeType = item.plans[0]
    if (!item.isPinned) setConfirmRemove({ ticker: item.ticker, type: removeType })
  }

  const executeRemove = async () => {
    if (!confirmRemove) return
    try { await removeMutation.mutateAsync(confirmRemove) } catch { /* handled by RQ */ }
    setConfirmRemove(null)
  }

  const handleNewTrade = (ticker: string, planType: 'SWING' | 'LONGTERM') => {
    window.location.href = `/trades?add=${ticker}&plan=${planType}`
  }

  const renderItem = (item: UnifiedWatchlistItem, tier: ReadinessTier) => {
    const bars = mergedSparklines?.[item.ticker]
    // Near Entry: full sparkline chart. Setting Up + Watching: lightweight direction text.
    const sparklineData = tier === 'near_entry' ? bars : undefined
    const priceChange = tier !== 'near_entry' ? compute30dChange(bars) : undefined
    // Loading state depends on which fetch batch this ticker belongs to
    const isAboveFold = tier === 'near_entry' ||
      (tier === 'setting_up' && item.urgencyScore >= HOT_URGENCY_THRESHOLD)
    const loading = isAboveFold ? unified.sparklinesLoading : overflowSparklinesLoading

    return (
      <Fragment key={item.ticker}>
        <UnifiedRow
          item={item}
          sparklineData={sparklineData}
          priceChange={priceChange}
          sparklinesLoading={loading}
          isExpanded={expandedTicker === item.ticker}
          onToggleExpand={() => setExpandedTicker(
            (previous) => previous === item.ticker ? null : item.ticker,
          )}
          onEdit={setEditItem}
          onRemove={handleRemove}
          onUpdateRsi={(ticker) => updateRsiMutation.mutate(ticker)}
          onTogglePin={(ticker, pinned) =>
            editMutation.mutate({ ticker, type: 'swing', is_pinned: pinned, pin_reason: null })
          }
        />
        {expandedTicker === item.ticker && (
          <TableRow className="hover:bg-transparent">
            <TableCell colSpan={5} className="p-0 border-b border-border/30 whitespace-normal">
              <WatchlistDetailPanel item={item} onNewTrade={handleNewTrade} />
            </TableCell>
          </TableRow>
        )}
      </Fragment>
    )
  }

  if (unified.isLoading) {
    return <div className="flex justify-center py-12"><Spinner className="h-6 w-6" /></div>
  }
  if (unified.error) {
    return <ErrorState description="Could not load watchlist." retry={unified.refetch} />
  }
  if (!unified.items?.length) {
    return <EmptyState icon={List} title="No stocks" description="Your watchlist is empty. Add stocks to start tracking." />
  }

  return (
    <>
      {/* Filter bar */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <FilterButton active={planFilter === 'all'} onClick={() => setPlanFilter('all')}>
            All <span className="text-muted-foreground ml-1">{totalCount}</span>
          </FilterButton>
          <FilterButton active={planFilter === 'swing'} onClick={() => setPlanFilter('swing')}>
            Swing
          </FilterButton>
          <FilterButton active={planFilter === 'longterm'} onClick={() => setPlanFilter('longterm')}>
            Long-Term
          </FilterButton>
          {nearEntryCount > 0 && (
            <Badge className="bg-emerald-500/15 text-emerald-400 text-[10px] ml-2">
              {nearEntryCount} near entry
            </Badge>
          )}
        </div>
        <Button variant="ghost" size="sm" onClick={() => setAddDialogOpen(true)} data-test-id="add-watchlist">
          <Plus className="size-4" /> Add
        </Button>
      </div>

      {/* Readiness-tiered table */}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="min-w-[180px]">Ticker</TableHead>
            <TableHead className="text-right min-w-[160px]">
              <ColumnInfo label="Signal" tip="RSI zone (swing) or entry proximity (long-term)" className="justify-end" />
            </TableHead>
            <TableHead className="text-right min-w-[100px]">
              <ColumnInfo label="Price" tip="Last closing price" className="justify-end" />
            </TableHead>
            <TableHead className="min-w-[100px]">30d</TableHead>
            <TableHead className="w-[70px]" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {filteredGroups?.map((group) => {
            const { tier, items } = group
            const config = READINESS_CONFIG[tier]
            const overflowExpanded = expandedOverflows.has(tier)

            // Near Entry: all visible. Setting Up: split at urgency threshold. Watching: all collapsed.
            let hotItems: UnifiedWatchlistItem[]
            let overflowItems: UnifiedWatchlistItem[]
            let overflowLabel: string

            if (tier === 'near_entry') {
              hotItems = items
              overflowItems = []
              overflowLabel = ''
            } else if (tier === 'setting_up') {
              hotItems = items.filter((item) => item.urgencyScore >= HOT_URGENCY_THRESHOLD)
              overflowItems = items.filter((item) => item.urgencyScore < HOT_URGENCY_THRESHOLD)
              overflowLabel = `${overflowItems.length} more approaching`
            } else {
              hotItems = []
              overflowItems = items
              overflowLabel = `${items.length} stocks watching`
            }

            return (
              <Fragment key={tier}>
                {/* Tier header */}
                <TableRow className="hover:bg-transparent">
                  <TableCell colSpan={5} className="py-2">
                    <div className="flex items-center gap-2">
                      <Badge className={cn('text-[10px] px-2 py-0 h-4', config.badgeClass)}>
                        {config.label}
                      </Badge>
                      <span className="text-[10px] text-muted-foreground/60 font-mono">
                        {items.length}
                      </span>
                      {tier === 'near_entry' && items.length === 0 && (
                        <span className="text-[10px] text-muted-foreground italic">
                          Nothing actionable today
                        </span>
                      )}
                    </div>
                  </TableCell>
                </TableRow>

                {/* Hot items — always visible as full rows */}
                {hotItems.map((item) => renderItem(item, tier))}

                {/* Overflow — collapsed by default */}
                {overflowItems.length > 0 && (
                  <>
                    <TableRow className="hover:bg-transparent">
                      <TableCell colSpan={5} className="py-1.5">
                        <button
                          type="button"
                          onClick={() => toggleOverflow(tier)}
                          className="flex items-center gap-1 text-[11px] text-muted-foreground/50 hover:text-muted-foreground transition-colors cursor-pointer"
                        >
                          <ChevronRight className={cn(
                            'h-3 w-3 transition-transform duration-150',
                            overflowExpanded && 'rotate-90',
                          )} />
                          {overflowLabel}
                        </button>
                      </TableCell>
                    </TableRow>
                    {overflowExpanded && overflowItems.map((item) => renderItem(item, tier))}
                  </>
                )}
              </Fragment>
            )
          })}
        </TableBody>
      </Table>

      <WatchlistDialog open={addDialogOpen} onOpenChange={setAddDialogOpen} defaultTicker={addTicker} />
      {editItem && (
        <WatchlistEditDialog open={!!editItem} item={editItem as any} type={editItem.plans[0]}
          onOpenChange={(open) => { if (!open) setEditItem(null) }} />
      )}
      <ConfirmDialog open={!!confirmRemove} confirmText="Remove"
        onOpenChange={(open) => { if (!open) setConfirmRemove(null) }}
        title={`Remove ${confirmRemove?.ticker}?`}
        description={`Remove ${confirmRemove?.ticker} from ${confirmRemove?.type === 'longterm' ? 'long-term' : 'swing'} watchlist?`}
        onConfirm={executeRemove} isPending={removeMutation.isPending} />
    </>
  )
}

function FilterButton({ active, onClick, children }: {
  active: boolean; onClick: () => void; children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'px-3 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer',
        active ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50',
      )}
    >
      {children}
    </button>
  )
}
