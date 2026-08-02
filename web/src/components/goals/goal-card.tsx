import { useState, useMemo } from 'react'
import { MoreVertical, Pencil, Trash2, ChevronRight } from 'lucide-react'
import { Card } from '../ui/card'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import {
  Collapsible,
  CollapsibleContent,
} from '../ui/collapsible'
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu'
import type { Goal, Trade } from '../../types/index'
import { formatCompact, formatVND, formatPct, plColor, toTitleCase } from '../../lib/utils'
import dayjs from 'dayjs'
import { formatMinDate, parseDate, toDateStr } from '../../lib/date'

const formatDate = (date: string | null) => {
  if (!date) return '-'
  return formatMinDate(date)
}

const STATUS_STYLES: Record<string, { text: string; bg: string; bar: string }> = {
  Active: {
    text: 'text-blue-500',
    bg: 'bg-blue-500/20',
    bar: 'bg-blue-500',
  },
  Achieved: {
    text: 'text-emerald-500',
    bg: 'bg-emerald-500/20',
    bar: 'bg-emerald-500',
  },
  Failed: {
    text: 'text-rose-500',
    bg: 'bg-rose-500/20',
    bar: 'bg-rose-500',
  },
  Paused: {
    text: 'text-amber-500',
    bg: 'bg-amber-500/20',
    bar: 'bg-amber-500',
  },
  Tracking: {
    text: 'text-violet-500',
    bg: 'bg-violet-500/20',
    bar: 'bg-violet-500',
  },
}

const DEFAULT_STYLE = {
  text: 'text-muted-foreground',
  bg: 'bg-muted',
  bar: 'bg-muted-foreground',
}

function getDaysRemaining(deadline: string): number {
  return parseDate(deadline).diff(parseDate(dayjs().format('YYYY-MM-DD')), 'day')
}

function getGoalTrades(goal: Goal, trades: Trade[]): Trade[] {
  const start = toDateStr(goal.start_date)
  const end = toDateStr(goal.deadline)
  return trades.filter((t) => {
    if (t.status !== 'CLOSED' || !t.exit_date) return false
    const exitDay = toDateStr(t.exit_date)
    return exitDay >= start && exitDay <= end
  })
}

export interface GoalCardProps {
  goal: Goal
  trades: Trade[]
  onEdit: () => void
  onDelete: () => void
}

export function GoalCard({ goal, trades, onEdit, onDelete }: GoalCardProps) {
  const [expanded, setExpanded] = useState(false)
  const statusKey = goal.status ?? 'Active'
  const styles = STATUS_STYLES[statusKey] ?? DEFAULT_STYLE
  const percentage = goal.target_vnd > 0
    ? Math.min((Number(goal.realized_vnd) / Number(goal.target_vnd)) * 100, 150)
    : 0
  const displayPercentage = Math.round(percentage)
  const daysRemaining = getDaysRemaining(goal.deadline)
  const remaining = Number(goal.target_vnd) - Number(goal.realized_vnd)

  const goalTrades = useMemo(() => getGoalTrades(goal, trades), [goal, trades])
  const wins = goalTrades.filter((t) => t.result === 'WIN').length
  const losses = goalTrades.filter((t) => t.result === 'LOSS').length

  return (
    <Card className="border-border/50 overflow-hidden py-0">
      <Collapsible open={expanded} onOpenChange={setExpanded}>
        <div
          className="p-4 cursor-pointer hover:bg-muted/30 transition-colors"
          onClick={() => setExpanded(!expanded)}
        >
          <div className="flex items-start justify-between gap-4 mb-3">
            <div className="flex items-start gap-2 flex-1 min-w-0">
              <ChevronRight
                className={`h-4 w-4 mt-1 shrink-0 text-muted-foreground transition-transform duration-200 ${expanded ? 'rotate-90' : ''}`}
              />
              <div className="flex-1 min-w-0">
                <h3 className="font-medium truncate">{goal.name}</h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Target: {formatCompact(goal.target_vnd)} · Realized: {formatVND(goal.realized_vnd)}
                  {statusKey === 'Active' && daysRemaining > 0 && (
                    <> · {daysRemaining}d remaining</>
                  )}
                  {statusKey === 'Active' && daysRemaining <= 0 && (
                    <> · Deadline passed</>
                  )}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0" onClick={(e) => e.stopPropagation()}>
              <span className="font-mono tabular-nums text-sm font-medium">
                {displayPercentage}%
              </span>
              <Badge variant="outline" className={`text-[10px] tracking-wider border-0 ${styles.bg} ${styles.text}`}>
                {statusKey}
              </Badge>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-8 w-8">
                    <MoreVertical className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={onEdit}>
                    <Pencil className="h-4 w-4" />
                    Edit
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={onDelete} className="text-destructive focus:text-destructive">
                    <Trash2 className="h-4 w-4" />
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>

          <div className="h-1.5 bg-muted rounded-full overflow-hidden ml-6">
            <div
              className={`h-full rounded-full transition-all duration-500 ${styles.bar}`}
              style={{ width: `${Math.max(Math.min(percentage, 100), 0)}%` }}
            />
          </div>

          {statusKey === 'Active' && (
            <p className="text-xs text-muted-foreground mt-2 font-mono tabular-nums ml-6">
              {remaining > 0 ? (
                <>{formatCompact(remaining)} to go</>
              ) : (
                <span className="text-emerald-500">+{formatCompact(Math.abs(remaining))} over target</span>
              )}
            </p>
          )}
          {statusKey === 'Achieved' && (
            <p className="text-xs text-emerald-500 mt-2 font-mono tabular-nums ml-6">
              +{formatCompact(Number(goal.realized_vnd) - Number(goal.target_vnd))} over target
            </p>
          )}
          {statusKey === 'Failed' && (
            <p className="text-xs text-rose-500 mt-2 font-mono tabular-nums ml-6">
              Missed by {formatCompact(Math.abs(remaining))}
            </p>
          )}
        </div>

        <CollapsibleContent>
          <div className="border-t border-border/50 bg-muted/20">
            {goalTrades.length === 0 ? (
              <p className="text-xs text-muted-foreground px-4 py-3 pl-10">
                No closed trades in this period
              </p>
            ) : (
              <Table className="text-xs">
                <TableHeader>
                  <TableRow className="hover:bg-transparent border-border/30">
                    <TableHead className="h-7 pl-10 text-[10px] uppercase tracking-wider">Ticker</TableHead>
                    <TableHead className="h-7 text-[10px] uppercase tracking-wider">Exit</TableHead>
                    <TableHead className="h-7 text-right text-[10px] uppercase tracking-wider">P/L</TableHead>
                    <TableHead className="h-7 text-right text-[10px] uppercase tracking-wider">Result</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {goalTrades.map((trade) => (
                    <TableRow key={trade.id} className="hover:bg-transparent border-border/30">
                      <TableCell className="py-1.5 pl-10 font-medium font-mono">{trade.ticker}</TableCell>
                      <TableCell className="py-1.5 text-muted-foreground tabular-nums">{formatDate(trade.exit_date)}</TableCell>
                      <TableCell className={`py-1.5 text-right font-mono tabular-nums ${plColor(trade.pl_net_vnd)}`}>
                        {formatVND(trade.pl_net_vnd)}
                      </TableCell>
                      <TableCell className="py-1.5 text-right">
                        <Badge
                          variant={trade.result === 'WIN' ? 'default' : 'destructive'}
                          className={`text-[10px] px-1.5 py-0 ${trade.result === 'WIN' ? 'bg-emerald-500 hover:bg-emerald-500/80' : ''}`}
                        >
                          {toTitleCase(trade.result)}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
                <TableFooter className="bg-transparent border-border/30">
                  <TableRow className="hover:bg-transparent">
                    <TableCell colSpan={2} className="py-3 pl-10 text-[11px]">
                      {goalTrades.length} trade{goalTrades.length !== 1 ? 's' : ''}
                      {' · '}
                      <span className="text-emerald-500">{wins}W</span>
                      {' '}
                      <span className="text-rose-500">{losses}L</span>
                    </TableCell>
                    <TableCell colSpan={2} className={`py-3 text-right font-mono tabular-nums font-medium ${plColor(Number(goal.realized_vnd))}`}>
                      Net: {formatVND(Number(goal.realized_vnd))}
                    </TableCell>
                  </TableRow>
                </TableFooter>
              </Table>
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  )
}
