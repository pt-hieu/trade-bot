import { useEffect } from 'react'
import { useForm, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from './ui/dialog'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Label } from './ui/label'
import { Textarea } from './ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select'
import { Spinner } from './ui/spinner'
import { useCreateCatalyst, useUpdateCatalyst } from '../hooks/use-catalysts'
import type { Catalyst, CatalystInput } from '../types/index'

interface CatalystDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  catalyst?: Catalyst
}

const IMPACTS = ['POSITIVE', 'NEGATIVE', 'NEUTRAL'] as const
const CONFIDENCES = ['HIGH', 'MEDIUM', 'LOW'] as const
const STATUSES = ['active', 'monitoring', 'imminent', 'resolved', 'expired'] as const

const catalystSchema = z.object({
  catalyst_key: z.string().min(1, 'Required').max(60),
  event: z.string().min(1, 'Required'),
  expected: z.string().min(1, 'Required'),
  affected_tickers_str: z.string(),
  impact: z.enum(IMPACTS),
  confidence: z.enum(CONFIDENCES),
  status: z.enum(STATUSES),
  notes: z.string().nullable(),
  source: z.string().nullable(),
  outcome: z.string().nullable(),
  actual_date: z.string().nullable(),
  expected_date: z.string().nullable(),
})

type CatalystFormData = z.infer<typeof catalystSchema>

import { FieldError } from './ui/field-error'

export function CatalystDialog({ open, onOpenChange, catalyst }: CatalystDialogProps) {
  const createCatalyst = useCreateCatalyst()
  const updateCatalyst = useUpdateCatalyst()
  const isEditing = !!catalyst

  const {
    register,
    handleSubmit,
    control,
    reset,
    watch,
    formState: { errors },
  } = useForm<CatalystFormData>({
    resolver: zodResolver(catalystSchema),
    defaultValues: {
      catalyst_key: '',
      event: '',
      expected: '',
      affected_tickers_str: '',
      impact: 'POSITIVE',
      confidence: 'MEDIUM',
      status: 'active',
      notes: null,
      source: null,
      outcome: null,
      actual_date: null,
      expected_date: null,
    },
  })

  const watchStatus = watch('status')

  useEffect(() => {
    if (open && catalyst) {
      reset({
        catalyst_key: catalyst.catalyst_key,
        event: catalyst.event,
        expected: catalyst.expected,
        affected_tickers_str: catalyst.affected_tickers?.join(', ') ?? '',
        impact: catalyst.impact,
        confidence: catalyst.confidence,
        status: catalyst.status,
        notes: catalyst.notes,
        source: catalyst.source,
        outcome: catalyst.outcome,
        actual_date: catalyst.actual_date,
        expected_date: catalyst.expected_date,
      })
    } else if (open) {
      reset({
        catalyst_key: '',
        event: '',
        expected: '',
        affected_tickers_str: '',
        impact: 'POSITIVE',
        confidence: 'MEDIUM',
        status: 'active',
        notes: null,
        source: null,
        outcome: null,
        actual_date: null,
        expected_date: null,
      })
    }
  }, [open, catalyst, reset])

  const onSubmit = async (data: CatalystFormData) => {
    const tickers = data.affected_tickers_str
      .split(',')
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean)

    const isTerminal = data.status === 'resolved' || data.status === 'expired'
    const input: CatalystInput = {
      catalyst_key: data.catalyst_key,
      event: data.event,
      expected: data.expected,
      affected_tickers: tickers,
      impact: data.impact,
      confidence: data.confidence,
      status: data.status,
      notes: data.notes || null,
      source: data.source || null,
      outcome: isTerminal ? (data.outcome || null) : null,
      actual_date: isTerminal ? (data.actual_date || null) : null,
      expected_date: data.expected_date || null,
    }

    try {
      if (isEditing) {
        await updateCatalyst.mutateAsync({ id: String(catalyst.id), input })
      } else {
        await createCatalyst.mutateAsync(input)
      }
      onOpenChange(false)
    } catch (error) {
      console.error('Failed to save catalyst:', error)
    }
  }

  const isPending = createCatalyst.isPending || updateCatalyst.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit Catalyst' : 'New Catalyst'}</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="catalystKey">Key <span className="text-destructive">*</span></Label>
              <Input id="catalystKey" {...register('catalyst_key')} placeholder="ftse_upgrade" maxLength={60} />
              <FieldError message={errors.catalyst_key?.message} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="expected">Expected <span className="text-destructive">*</span></Label>
              <Input id="expected" {...register('expected')} placeholder="Q1-Q2 2026" />
              <FieldError message={errors.expected?.message} />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="event">Event <span className="text-destructive">*</span></Label>
            <Input id="event" {...register('event')} placeholder="FTSE Emerging Market upgrade" />
            <FieldError message={errors.event?.message} />
          </div>

          <div className="space-y-2">
            <Label htmlFor="tickers">Affected tickers</Label>
            <Input id="tickers" {...register('affected_tickers_str')} placeholder="FPT, VHM, TCB" />
            <p className="text-xs text-muted-foreground">Comma-separated</p>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label>Impact</Label>
              <Controller name="impact" control={control} render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {IMPACTS.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}
                  </SelectContent>
                </Select>
              )} />
            </div>
            <div className="space-y-2">
              <Label>Confidence</Label>
              <Controller name="confidence" control={control} render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {CONFIDENCES.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}
                  </SelectContent>
                </Select>
              )} />
            </div>
            <div className="space-y-2">
              <Label>Status</Label>
              <Controller name="status" control={control} render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {STATUSES.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}
                  </SelectContent>
                </Select>
              )} />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="source">Source URL</Label>
            <Input id="source" {...register('source')} placeholder="https://..." />
          </div>

          <div className="space-y-2">
            <Label htmlFor="notes">Notes</Label>
            <Textarea id="notes" {...register('notes')} placeholder="Optional notes..." rows={2} />
          </div>

          <div className="space-y-2">
            <Label htmlFor="expectedDate">Expected date</Label>
            <Input id="expectedDate" {...register('expected_date')} placeholder="2026-04-15" />
            <p className="text-xs text-muted-foreground">ISO date (YYYY-MM-DD), optional</p>
          </div>

          {(watchStatus === 'resolved' || watchStatus === 'expired') && (
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="actualDate">Actual date</Label>
                <Input id="actualDate" {...register('actual_date')} placeholder="2026-03-15" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="outcome">Outcome</Label>
                <Input id="outcome" {...register('outcome')} placeholder="Result..." />
              </div>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-4">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? <><Spinner /> Saving...</> : 'Save'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
