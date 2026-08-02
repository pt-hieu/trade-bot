import { useState } from 'react'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from './ui/table'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from './ui/dropdown-menu'
import { ConfirmDialog } from './ui/confirm-dialog'
import { EmptyState } from './ui/empty-state'
import { ErrorState } from './ui/error-state'
import { Skeleton } from './ui/skeleton'
import { CapitalEventDialog } from './capital-event-dialog'
import { useCapitalEvents, useDeleteCapitalEvent } from '../hooks/use-catalysts'
import { Landmark, MoreVertical, Pencil, Trash2 } from 'lucide-react'
import { impactBadge, statusBadge, EVENT_TYPE_LABELS, IMPACT_LABELS } from './catalysts-utils'
import type { CapitalEvent } from '../types/index'

function TableSkeleton() {
  return Array.from({ length: 3 }).map((_, i) => (
    <TableRow key={i}>
      {Array.from({ length: 8 }).map((_, j) => (
        <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
      ))}
    </TableRow>
  ))
}

export function CapitalEventsTable() {
  const { data: events, isLoading, error, refetch } = useCapitalEvents()
  const deleteEvent = useDeleteCapitalEvent()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [selected, setSelected] = useState<CapitalEvent | undefined>()
  const [deleteTarget, setDeleteTarget] = useState<CapitalEvent | undefined>()
  const [confirmOpen, setConfirmOpen] = useState(false)

  const handleNew = () => { setSelected(undefined); setDialogOpen(true) }
  const handleEdit = (e: CapitalEvent) => { setSelected(e); setDialogOpen(true) }

  if (error) return <ErrorState description="Could not load capital events." retry={refetch} />

  return (
    <>
      <div className="flex justify-end mb-4">
        <Button onClick={handleNew} size="sm" data-test-id="new-capital-event-btn">+ New Event</Button>
      </div>

      {isLoading ? (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Ticker</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Expected</TableHead>
                <TableHead className="text-right">Dilution</TableHead>
                <TableHead>Impact</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-[60px]" />
              </TableRow>
            </TableHeader>
            <TableBody><TableSkeleton /></TableBody>
          </Table>
        </div>
      ) : !events?.length ? (
        <EmptyState
          icon={Landmark}
          title="No capital events tracked"
          description="Add capital events like IPOs, capital increases, or M&A to monitor their impact."
          action={{ label: '+ New Event', onClick: handleNew }}
        />
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Ticker</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Expected</TableHead>
                <TableHead className="text-right">Dilution</TableHead>
                <TableHead>Impact</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-[60px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.map((e) => (
                <TableRow key={e.id} data-test-id={`capital-event-row-${e.id}`}>
                  <TableCell className="font-medium font-mono">{e.ticker}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs">
                      {EVENT_TYPE_LABELS[e.event_type] ?? e.event_type}
                    </Badge>
                  </TableCell>
                  <TableCell className="max-w-xs truncate">{e.description}</TableCell>
                  <TableCell className="whitespace-nowrap text-sm">{e.expected_date}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {e.dilution_pct != null ? `${e.dilution_pct}%` : '—'}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={impactBadge(e.impact)}>
                      {IMPACT_LABELS[e.impact] ?? e.impact}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={statusBadge(e.status)}>{e.status.charAt(0).toUpperCase() + e.status.slice(1)}</Badge>
                  </TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-accent cursor-pointer"
                        data-test-id={`capital-event-actions-${e.id}`}
                      >
                        <MoreVertical className="h-4 w-4" />
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => handleEdit(e as any)} className="cursor-pointer">
                          <Pencil className="h-4 w-4" /> Edit
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          onClick={() => { setDeleteTarget(e as any); setConfirmOpen(true) }}
                          className="text-destructive focus:text-destructive cursor-pointer"
                        >
                          <Trash2 className="h-4 w-4" /> Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <CapitalEventDialog open={dialogOpen} onOpenChange={setDialogOpen} event={selected} />

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Delete Capital Event"
        description={`Delete "${deleteTarget?.description}"? This cannot be undone.`}
        confirmText="Delete"
        variant="destructive"
        onConfirm={async () => {
          if (!deleteTarget) return
          await deleteEvent.mutateAsync(String(deleteTarget.id))
          setConfirmOpen(false)
          setDeleteTarget(undefined)
        }}
        isPending={deleteEvent.isPending}
      />
    </>
  )
}
