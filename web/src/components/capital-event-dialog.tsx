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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select'
import { Spinner } from './ui/spinner'
import { useCreateCapitalEvent, useUpdateCapitalEvent } from '../hooks/use-catalysts'
import type { CapitalEvent, CapitalEventInput } from '../types/index'

interface CapitalEventDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  event?: CapitalEvent
}

const EVENT_TYPES = [
  'capital_increase', 'ipo', 'stock_split', 'ma', 'buyback', 'dividend',
] as const

const EVENT_TYPE_LABELS: Record<string, string> = {
  capital_increase: 'Capital Increase',
  ipo: 'IPO',
  stock_split: 'Stock Split',
  ma: 'M&A',
  buyback: 'Buyback',
  dividend: 'Dividend',
}

const IMPACTS = [
  'POSITIVE', 'NEGATIVE_SHORT_TERM', 'NEGATIVE_LONG_TERM', 'WATCH',
] as const

const IMPACT_LABELS: Record<string, string> = {
  POSITIVE: 'Positive',
  NEGATIVE_SHORT_TERM: 'Negative (Short)',
  NEGATIVE_LONG_TERM: 'Negative (Long)',
  WATCH: 'Watch',
}

const STATUSES = ['pending', 'completed'] as const

const capitalEventSchema = z.object({
  event_key: z.string().min(1, 'Required').max(60),
  ticker: z.string().min(1, 'Required').max(20),
  event_type: z.enum(EVENT_TYPES),
  description: z.string().min(1, 'Required'),
  amount: z.string().nullable(),
  expected_date: z.string().min(1, 'Required'),
  dilution_pct: z.coerce.number().nullable(),
  impact: z.enum(IMPACTS),
  source: z.string().nullable(),
  status: z.enum(STATUSES),
})

type CapitalEventFormData = z.infer<typeof capitalEventSchema>

import { FieldError } from './ui/field-error'

export function CapitalEventDialog({ open, onOpenChange, event }: CapitalEventDialogProps) {
  const createEvent = useCreateCapitalEvent()
  const updateEvent = useUpdateCapitalEvent()
  const isEditing = !!event

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<CapitalEventFormData>({
    resolver: zodResolver(capitalEventSchema),
    defaultValues: {
      event_key: '',
      ticker: '',
      event_type: 'capital_increase',
      description: '',
      amount: null,
      expected_date: '',
      dilution_pct: null,
      impact: 'WATCH',
      source: null,
      status: 'pending',
    },
  })

  useEffect(() => {
    if (open && event) {
      reset({
        event_key: event.event_key,
        ticker: event.ticker,
        event_type: event.event_type,
        description: event.description,
        amount: event.amount,
        expected_date: event.expected_date,
        dilution_pct: event.dilution_pct,
        impact: event.impact,
        source: event.source,
        status: event.status,
      })
    } else if (open) {
      reset({
        event_key: '',
        ticker: '',
        event_type: 'capital_increase',
        description: '',
        amount: null,
        expected_date: '',
        dilution_pct: null,
        impact: 'WATCH',
        source: null,
        status: 'pending',
      })
    }
  }, [open, event, reset])

  const onSubmit = async (data: CapitalEventFormData) => {
    const input: CapitalEventInput = {
      event_key: data.event_key,
      ticker: data.ticker.toUpperCase(),
      event_type: data.event_type,
      description: data.description,
      amount: data.amount || null,
      expected_date: data.expected_date,
      dilution_pct: data.dilution_pct,
      impact: data.impact,
      source: data.source || null,
      status: data.status,
    }

    try {
      if (isEditing) {
        await updateEvent.mutateAsync({ id: String(event.id), input })
      } else {
        await createEvent.mutateAsync(input)
      }
      onOpenChange(false)
    } catch (error) {
      console.error('Failed to save capital event:', error)
    }
  }

  const isPending = createEvent.isPending || updateEvent.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit Capital Event' : 'New Capital Event'}</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="eventKey">Key <span className="text-destructive">*</span></Label>
              <Input id="eventKey" {...register('event_key')} placeholder="MBS_capital_increase" maxLength={60} />
              <FieldError message={errors.event_key?.message} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ticker">Ticker <span className="text-destructive">*</span></Label>
              <Input id="ticker" {...register('ticker')} placeholder="MBS" maxLength={20} />
              <FieldError message={errors.ticker?.message} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Event type <span className="text-destructive">*</span></Label>
              <Controller name="event_type" control={control} render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {EVENT_TYPES.map((v) => (
                      <SelectItem key={v} value={v}>{EVENT_TYPE_LABELS[v]}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="expectedDate">Expected date <span className="text-destructive">*</span></Label>
              <Input id="expectedDate" {...register('expected_date')} placeholder="Q2 2026" />
              <FieldError message={errors.expected_date?.message} />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">Description <span className="text-destructive">*</span></Label>
            <Input id="description" {...register('description')} placeholder="Increase charter capital by 500B VND" />
            <FieldError message={errors.description?.message} />
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label htmlFor="amount">Amount</Label>
              <Input id="amount" {...register('amount')} placeholder="500B VND" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="dilution">Dilution %</Label>
              <Input id="dilution" type="number" step="0.01" {...register('dilution_pct')} placeholder="15.0" />
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

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Impact</Label>
              <Controller name="impact" control={control} render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {IMPACTS.map((v) => (
                      <SelectItem key={v} value={v}>{IMPACT_LABELS[v]}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ceSource">Source URL</Label>
              <Input id="ceSource" {...register('source')} placeholder="https://..." />
            </div>
          </div>

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
