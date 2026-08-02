import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { TableRow, TableCell } from './ui/table'
import { Tooltip, TooltipTrigger, TooltipContent } from './ui/tooltip'
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
  DropdownMenuItem, DropdownMenuSeparator,
} from './ui/dropdown-menu'
import {
  Pin, PinOff, MoreVertical, RefreshCw, Pencil, Trash2, StickyNote, ChevronRight,
} from 'lucide-react'
import { cn } from '../lib/utils'
import { formatPriceVnd } from '../lib/watchlist-utils'
import type { PriceChange } from '../lib/watchlist-utils'
import { Sparkline } from './ui/sparkline'
import { Skeleton } from './ui/skeleton'
import type { UnifiedWatchlistItem } from '../lib/watchlist-merge'

interface UnifiedRowProps {
  item: UnifiedWatchlistItem
  /** Full sparkline chart — only for Near Entry rows. */
  sparklineData?: { close: number }[]
  /** Lightweight 30d direction — for Setting Up rows without full chart. */
  priceChange?: PriceChange
  /** True while sparkline data is still fetching. */
  sparklinesLoading?: boolean
  isExpanded: boolean
  onToggleExpand: () => void
  onEdit: (item: UnifiedWatchlistItem) => void
  onRemove: (item: UnifiedWatchlistItem) => void
  onUpdateRsi?: (ticker: string) => void
  onTogglePin?: (ticker: string, pinned: boolean) => void
}

const PLAN_BADGE: Record<string, string> = {
  swing: 'bg-blue-500/15 text-blue-400 border-blue-500/20',
  longterm: 'bg-purple-500/15 text-purple-400 border-purple-500/20',
}

export function UnifiedRow({
  item, sparklineData, priceChange, sparklinesLoading, isExpanded, onToggleExpand, onEdit, onRemove, onUpdateRsi, onTogglePin,
}: UnifiedRowProps) {
  const notes = item.swingNotes || item.longtermNotes
  const rowOpacity = item.readiness === 'watching' ? 'opacity-50'
    : item.readiness === 'setting_up' && item.urgencyScore < 0.3 ? 'opacity-55'
    : item.readiness === 'setting_up' && item.urgencyScore < 0.6 ? 'opacity-75'
    : undefined

  return (
    <TableRow
      className={cn('cursor-pointer', rowOpacity)}
      onClick={onToggleExpand}
    >
      {/* Ticker + plan badges + held indicator */}
      <TableCell className={cn('font-medium', item.readiness === 'near_entry' && 'font-semibold')}>
        <div className="flex items-center gap-1.5">
          <ChevronRight className={cn(
            'h-3.5 w-3.5 text-muted-foreground/50 shrink-0 transition-transform duration-150',
            isExpanded && 'rotate-90',
          )} />
          <span>{item.ticker}</span>
          {item.isPinned && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Pin className="h-3 w-3 text-amber-500 shrink-0" />
              </TooltipTrigger>
              <TooltipContent>{item.pinReason ?? 'Pinned'}</TooltipContent>
            </Tooltip>
          )}
          {item.plans.map((plan) => (
            <Badge key={plan} variant="outline" className={cn('text-[9px] px-1 py-0 h-3.5', PLAN_BADGE[plan])}>
              {plan === 'swing' ? 'Swing' : 'LT'}
            </Badge>
          ))}
          {item.heldShares != null && (
            <Badge variant="outline" className="text-[9px] px-1 py-0 h-3.5 text-emerald-400 border-emerald-500/20">
              Held {item.heldShares.toLocaleString()}
            </Badge>
          )}
        </div>
      </TableCell>

      {/* Signal — the "why now" metric */}
      <TableCell className="text-right">
        <SignalCell item={item} />
      </TableCell>

      {/* Current price */}
      <TableCell className="text-right font-mono tabular-nums text-sm">
        {item.currentPrice != null ? formatPriceVnd(item.currentPrice) : (
          <span className="text-muted-foreground">--</span>
        )}
      </TableCell>

      {/* 30d — sparkline chart for Near Entry, directional text for Setting Up */}
      <TableCell>
        {sparklineData ? (
          <Sparkline data={sparklineData} width={88} height={28} />
        ) : priceChange ? (
          <DirectionIndicator change={priceChange} />
        ) : sparklinesLoading ? (
          item.readiness === 'near_entry'
            ? <Skeleton className="h-7 w-[88px]" />
            : <Skeleton className="h-4 w-12" />
        ) : null}
      </TableCell>

      {/* Notes tooltip + Actions */}
      <TableCell onClick={(event) => event.stopPropagation()}>
        <div className="flex items-center gap-1">
          {notes && (
            <Tooltip>
              <TooltipTrigger asChild>
                <StickyNote className="h-3.5 w-3.5 text-muted-foreground/60 cursor-help" />
              </TooltipTrigger>
              <TooltipContent className="max-w-[240px]">{notes}</TooltipContent>
            </Tooltip>
          )}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-xs" data-test-id={`actions-${item.ticker}`}>
                <MoreVertical className="size-3" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => onEdit(item)}>
                <Pencil className="h-4 w-4" /> Edit
              </DropdownMenuItem>
              {item.plans.includes('swing') && onTogglePin && (
                item.isPinned ? (
                  <DropdownMenuItem onClick={() => onTogglePin(item.ticker, false)}>
                    <PinOff className="h-4 w-4" /> Unpin
                  </DropdownMenuItem>
                ) : (
                  <DropdownMenuItem onClick={() => onTogglePin(item.ticker, true)}>
                    <Pin className="h-4 w-4" /> Pin
                  </DropdownMenuItem>
                )
              )}
              {item.plans.includes('swing') && onUpdateRsi && (
                <DropdownMenuItem onClick={() => onUpdateRsi(item.ticker)}>
                  <RefreshCw className="h-4 w-4" /> Update RSI
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem
                disabled={item.isPinned}
                onClick={() => onRemove(item)}
                className="text-destructive focus:text-destructive"
              >
                <Trash2 className="h-4 w-4" /> Remove
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </TableCell>
    </TableRow>
  )
}

/** Renders the key signal metric based on plan type + readiness. */
function SignalCell({ item }: { item: UnifiedWatchlistItem }) {
  const signals: React.ReactNode[] = []

  // Swing RSI signal
  if (item.plans.includes('swing') && item.rsi != null && item.rsiBadgeClass) {
    signals.push(
      <Badge key="rsi" className={cn('font-mono tabular-nums gap-1', item.rsiBadgeClass)}>
        {item.rsi.toFixed(1)}
        <span className="text-[10px] font-sans opacity-80">{item.rsiLabel}</span>
      </Badge>
    )
  }

  // Long-term entry proximity signal
  if (item.plans.includes('longterm') && item.entryProximity) {
    const proximity = item.entryProximity
    signals.push(
      <span key="proximity" className={cn('text-xs font-mono tabular-nums font-medium', proximity.colorClass)}>
        {proximity.distancePct >= 0 ? '+' : ''}{proximity.distancePct.toFixed(1)}%
        <span className="text-[10px] font-sans opacity-80 ml-0.5">Entry</span>
      </span>
    )
  }

  if (signals.length === 0) return <span className="text-muted-foreground text-xs">--</span>
  return <div className="flex items-center justify-end gap-2">{signals}</div>
}

/** Lightweight 30d direction — arrow + percentage, no SVG chart. */
function DirectionIndicator({ change }: { change: PriceChange }) {
  return (
    <span className={cn(
      'text-xs font-mono tabular-nums',
      change.direction === 'up' ? 'text-emerald-400'
        : change.direction === 'down' ? 'text-rose-400'
        : 'text-muted-foreground',
    )}>
      {change.direction === 'up' ? '↑' : change.direction === 'down' ? '↓' : '→'}
      {' '}{Math.abs(change.pct).toFixed(1)}%
    </span>
  )
}
