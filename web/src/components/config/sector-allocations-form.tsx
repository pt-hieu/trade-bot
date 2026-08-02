import { useState } from 'react'
import { Trash2, Pencil, Check, X, Plus } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { Input } from '../ui/input'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import { Skeleton } from '../ui/skeleton'
import { ErrorState } from '../ui/error-state'
import { ConfirmDialog } from '../ui/confirm-dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { useSectorAllocations, useUpsertSectorAllocation, useDeleteSectorAllocation } from '../../hooks/use-sector-allocations'
import { useSectors } from '../../hooks/use-watchlist'
import { toTitleCase } from '../../lib/utils'
import type { SectorAllocation } from '../../types/index'

function AllocationRow({
  row,
  onEdit,
  onDelete,
  isDeleting,
}: {
  row: SectorAllocation
  onEdit: (row: SectorAllocation) => void
  onDelete: (row: SectorAllocation) => void
  isDeleting: boolean
}) {
  return (
    <tr className="border-b border-border/40 last:border-0">
      <td className="py-2.5 pr-4 text-sm">{toTitleCase(row.sector_name)}</td>
      <td className="py-2.5 pr-4 text-sm font-mono tabular-nums">{Number(row.target_pct).toFixed(1)}%</td>
      <td className="py-2.5">
        <div className="flex items-center gap-1.5">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-7 w-7 cursor-pointer"
            onClick={() => onEdit(row)}
            data-test-id={`edit-allocation-${row.sector_name}`}
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-destructive hover:text-destructive cursor-pointer"
            onClick={() => onDelete(row)}
            disabled={isDeleting}
            data-test-id={`delete-allocation-${row.sector_name}`}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </td>
    </tr>
  )
}

function EditRow({
  row,
  onSave,
  onCancel,
  isSaving,
}: {
  row: SectorAllocation
  onSave: (pct: number) => void
  onCancel: () => void
  isSaving: boolean
}) {
  const [pct, setPct] = useState(Number(row.target_pct))

  return (
    <tr className="border-b border-border/40 last:border-0 bg-muted/20">
      <td className="py-2 pr-4 text-sm">{toTitleCase(row.sector_name)}</td>
      <td className="py-2 pr-4">
        <Input
          type="number"
          min={0}
          max={100}
          step={0.5}
          value={pct}
          onChange={(e) => setPct(parseFloat(e.target.value) || 0)}
          className="h-7 w-24 text-sm"
          autoFocus
          data-test-id={`edit-pct-${row.sector_name}`}
        />
      </td>
      <td className="py-2">
        <div className="flex items-center gap-1.5">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-green-500 hover:text-green-400 cursor-pointer"
            onClick={() => onSave(pct)}
            disabled={isSaving}
            data-test-id={`save-allocation-${row.sector_name}`}
          >
            <Check className="h-3.5 w-3.5" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-7 w-7 cursor-pointer"
            onClick={onCancel}
            disabled={isSaving}
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      </td>
    </tr>
  )
}

function AddRow({
  sectors,
  existingNames,
  onAdd,
  isAdding,
}: {
  sectors: { name: string; display_name: string }[]
  existingNames: Set<string>
  onAdd: (name: string, pct: number) => void
  isAdding: boolean
}) {
  const [name, setName] = useState('')
  const [pct, setPct] = useState(0)
  const [useSelect, setUseSelect] = useState(true)
  const available = sectors.filter((s) => !existingNames.has(s.name))

  function handleAdd() {
    if (!name || pct <= 0) return
    onAdd(name, pct)
    setName('')
    setPct(0)
  }

  return (
    <tr className="border-t border-dashed border-border/60">
      <td className="pt-3 pr-4">
        {useSelect && available.length > 0 ? (
          <div className="flex items-center gap-1.5">
            <Select value={name} onValueChange={setName}>
              <SelectTrigger className="h-7 text-sm w-40" data-test-id="new-sector-select">
                <SelectValue placeholder="Pick sector" />
              </SelectTrigger>
              <SelectContent>
                {available.map((s) => (
                  <SelectItem key={s.name} value={s.name}>
                    {s.display_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <button
              type="button"
              className="text-xs text-muted-foreground hover:text-foreground cursor-pointer underline"
              onClick={() => { setUseSelect(false); setName('') }}
            >
              custom
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-1.5">
            <Input
              type="text"
              placeholder="e.g. securities"
              value={name}
              onChange={(e) => setName(e.target.value.toLowerCase().replace(/[^a-z_]/g, ''))}
              className="h-7 w-40 text-sm font-mono"
              data-test-id="new-sector-name"
            />
            {sectors.length > 0 && (
              <button
                type="button"
                className="text-xs text-muted-foreground hover:text-foreground cursor-pointer underline"
                onClick={() => { setUseSelect(true); setName('') }}
              >
                pick
              </button>
            )}
          </div>
        )}
      </td>
      <td className="pt-3 pr-4">
        <Input
          type="number"
          min={0}
          max={100}
          step={0.5}
          placeholder="0"
          value={pct || ''}
          onChange={(e) => setPct(parseFloat(e.target.value) || 0)}
          className="h-7 w-24 text-sm"
          data-test-id="new-sector-pct"
        />
      </td>
      <td className="pt-3">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7 cursor-pointer"
          onClick={handleAdd}
          disabled={!name || pct <= 0 || isAdding}
          data-test-id="add-sector-button"
        >
          <Plus className="h-3.5 w-3.5" />
        </Button>
      </td>
    </tr>
  )
}

function AllocationSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-3 w-64" />
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

export function SectorAllocationsForm() {
  const { data, isLoading, error, refetch } = useSectorAllocations()
  const { data: sectors = [] } = useSectors()
  const upsert = useUpsertSectorAllocation()
  const remove = useDeleteSectorAllocation()

  const [editingId, setEditingId] = useState<number | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<SectorAllocation | null>(null)

  if (isLoading) return <AllocationSkeleton />
  if (error) return <ErrorState description="Could not load sector allocations." retry={refetch} />

  const rows = data ?? []
  const total = rows.reduce((sum, r) => sum + Number(r.target_pct), 0)
  const totalOk = Math.abs(total - 100) < 0.01
  const existingNames = new Set(rows.map((r) => r.sector_name))

  async function handleSave(row: SectorAllocation, pct: number) {
    await upsert.mutateAsync({ sector_name: row.sector_name, target_pct: pct })
    setEditingId(null)
  }

  async function handleAdd(name: string, pct: number) {
    await upsert.mutateAsync({ sector_name: name, target_pct: pct })
  }

  async function handleDelete() {
    if (!confirmDelete) return
    await remove.mutateAsync(confirmDelete.sector_name)
    setConfirmDelete(null)
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold tracking-wide uppercase text-muted-foreground">
            Sector Allocations
          </CardTitle>
          <CardDescription>
            Target allocation percentages for long-term portfolio. Must sum to 100%.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <table className="w-full">
            <thead>
              <tr className="border-b border-border text-xs text-muted-foreground">
                <th className="pb-2 pr-4 text-left font-medium">Sector</th>
                <th className="pb-2 pr-4 text-left font-medium">Target</th>
                <th className="pb-2 text-left font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) =>
                editingId === row.id ? (
                  <EditRow
                    key={row.id}
                    row={row}
                    onSave={(pct) => handleSave(row, pct)}
                    onCancel={() => setEditingId(null)}
                    isSaving={upsert.isPending}
                  />
                ) : (
                  <AllocationRow
                    key={row.id}
                    row={row}
                    onEdit={(r) => setEditingId(r.id)}
                    onDelete={(r) => setConfirmDelete(r)}
                    isDeleting={remove.isPending}
                  />
                )
              )}
              <AddRow
                sectors={sectors as any}
                existingNames={existingNames}
                onAdd={handleAdd}
                isAdding={upsert.isPending}
              />
            </tbody>
            <tfoot>
              <tr>
                <td className="pt-3 pr-4 text-sm font-medium text-muted-foreground">Total</td>
                <td className="pt-3 pr-4">
                  <span className="text-sm font-mono tabular-nums font-semibold">
                    {total.toFixed(1)}%
                  </span>
                </td>
                <td className="pt-3">
                  {!totalOk && rows.length > 0 && (
                    <Badge variant="outline" className="text-xs text-amber-500 border-amber-500/40">
                      Should sum to 100%
                    </Badge>
                  )}
                </td>
              </tr>
            </tfoot>
          </table>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={!!confirmDelete}
        onOpenChange={(open) => { if (!open) setConfirmDelete(null) }}
        title="Remove sector allocation"
        description={`Remove ${confirmDelete ? toTitleCase(confirmDelete.sector_name) : ''} from sector allocations?`}
        confirmText="Remove"
        onConfirm={handleDelete}
        isPending={remove.isPending}
      />
    </>
  )
}
