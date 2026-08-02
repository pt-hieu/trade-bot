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
import { CatalystDialog } from './catalyst-dialog'
import { useCatalysts, useDeleteCatalyst } from '../hooks/use-catalysts'
import { Zap, MoreVertical, Pencil, Trash2 } from 'lucide-react'
import { impactBadge, confidenceBadge, statusBadge, IMPACT_LABELS } from './catalysts-utils'
import type { Catalyst } from '../types/index'

function TableSkeleton() {
  return Array.from({ length: 3 }).map((_, i) => (
    <TableRow key={i}>
      {Array.from({ length: 7 }).map((_, j) => (
        <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
      ))}
    </TableRow>
  ))
}

export function CatalystsTable() {
  const { data: catalysts, isLoading, error, refetch } = useCatalysts()
  const deleteCatalyst = useDeleteCatalyst()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [selected, setSelected] = useState<Catalyst | undefined>()
  const [deleteTarget, setDeleteTarget] = useState<Catalyst | undefined>()
  const [confirmOpen, setConfirmOpen] = useState(false)

  const handleNew = () => { setSelected(undefined); setDialogOpen(true) }
  const handleEdit = (c: Catalyst) => { setSelected(c); setDialogOpen(true) }

  if (error) return <ErrorState description="Could not load catalysts." retry={refetch} />

  return (
    <>
      <div className="flex justify-end mb-4">
        <Button onClick={handleNew} size="sm" data-test-id="new-catalyst-btn">+ New Catalyst</Button>
      </div>

      {isLoading ? (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Event</TableHead>
                <TableHead>Expected</TableHead>
                <TableHead>Tickers</TableHead>
                <TableHead>Impact</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-[60px]" />
              </TableRow>
            </TableHeader>
            <TableBody><TableSkeleton /></TableBody>
          </Table>
        </div>
      ) : !catalysts?.length ? (
        <EmptyState
          icon={Zap}
          title="No catalysts tracked"
          description="Add market catalysts to track upcoming events that may affect your portfolio."
          action={{ label: '+ New Catalyst', onClick: handleNew }}
        />
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Event</TableHead>
                <TableHead>Expected</TableHead>
                <TableHead>Tickers</TableHead>
                <TableHead>Impact</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-[60px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {catalysts.map((c) => (
                <TableRow key={c.id} data-test-id={`catalyst-row-${c.id}`}>
                  <TableCell className="max-w-[280px]">
                    <div className="font-medium truncate">{c.event}</div>
                    {c.notes && <div className="text-xs text-muted-foreground mt-0.5 truncate">{c.notes}</div>}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-sm">{c.expected}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {c.affected_tickers?.map((t: any) => (
                        <Badge key={t} variant="outline" className="font-mono text-xs px-1.5 py-0">{t}</Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={impactBadge(c.impact)}>
                      {IMPACT_LABELS[c.impact] ?? c.impact}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={confidenceBadge(c.confidence)}>{c.confidence.charAt(0) + c.confidence.slice(1).toLowerCase()}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={statusBadge(c.status)}>{c.status.charAt(0).toUpperCase() + c.status.slice(1)}</Badge>
                  </TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-accent cursor-pointer"
                        data-test-id={`catalyst-actions-${c.id}`}
                      >
                        <MoreVertical className="h-4 w-4" />
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => handleEdit(c as any)} className="cursor-pointer">
                          <Pencil className="h-4 w-4" /> Edit
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          onClick={() => { setDeleteTarget(c as any); setConfirmOpen(true) }}
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

      <CatalystDialog open={dialogOpen} onOpenChange={setDialogOpen} catalyst={selected} />

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Delete Catalyst"
        description={`Delete "${deleteTarget?.event}"? This cannot be undone.`}
        confirmText="Delete"
        variant="destructive"
        onConfirm={async () => {
          if (!deleteTarget) return
          await deleteCatalyst.mutateAsync(String(deleteTarget.id))
          setConfirmOpen(false)
          setDeleteTarget(undefined)
        }}
        isPending={deleteCatalyst.isPending}
      />
    </>
  )
}
