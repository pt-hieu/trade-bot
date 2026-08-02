import { useEffect } from 'react'
import { useForm, Controller, useFieldArray } from 'react-hook-form'
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
import { useCreateAlert, useUpdateAlert } from '../hooks/use-alerts'
import { toTitleCase } from '../lib/utils'
import { Plus, X } from 'lucide-react'
import type { Alert, AlertConditionType, AlertAction } from '../types/index'

interface AlertDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  alert?: Alert
}

const CONDITION_TYPES: { value: AlertConditionType; label: string }[] = [
  { value: 'price_below', label: 'Price below' },
  { value: 'price_above', label: 'Price above' },
  { value: 'rsi_below', label: 'RSI below' },
  { value: 'rsi_above', label: 'RSI above' },
  { value: 'volume_spike', label: 'Volume spike' },
]

const ACTIONS: AlertAction[] = ['BUY', 'TRIM', 'EXIT', 'ADD', 'WATCH']
const PRIORITIES = ['high', 'normal', 'low'] as const

const conditionSchema = z.object({
  type: z.enum(['price_below', 'price_above', 'rsi_below', 'rsi_above', 'volume_spike']),
  value: z.coerce.number().min(0.01, 'Must be > 0'),
})

const alertSchema = z.object({
  ticker: z.string().min(1, 'Required').max(10, 'Max 10 chars'),
  conditions: z
    .array(conditionSchema)
    .min(1, 'At least one condition')
    .max(5, 'Max 5 conditions'),
  condition_logic: z.enum(['ALL', 'ANY']),
  recommended_action: z.enum(['BUY', 'TRIM', 'EXIT', 'ADD', 'WATCH']).nullable(),
  priority: z.enum(['high', 'normal', 'low']),
  rationale: z.string().nullable(),
})

type AlertFormData = z.infer<typeof alertSchema>

import { FieldError } from './ui/field-error'
import { CONDITION_DEFAULT_ACTION, ConditionPreview } from './alerts/components'

export function AlertDialog({ open, onOpenChange, alert }: AlertDialogProps) {
  const createAlert = useCreateAlert()
  const updateAlert = useUpdateAlert()
  const isEditing = !!alert

  const {
    register,
    handleSubmit,
    control,
    reset,
    watch,
    setValue,
    formState: { errors },
  } = useForm<AlertFormData>({
    resolver: zodResolver(alertSchema),
    defaultValues: {
      ticker: '',
      conditions: [{ type: 'price_below', value: '' as unknown as number }],
      condition_logic: 'ALL',
      recommended_action: null,
      priority: 'normal',
      rationale: null,
    },
  })

  const { fields, append, remove } = useFieldArray({
    control,
    name: 'conditions',
  })

  useEffect(() => {
    if (open && alert) {
      const conditionsFromAlert = alert.conditions?.map((condition) => ({
        type: condition.condition_type,
        value: condition.condition_value ?? ('' as unknown as number),
      })) ?? [{ type: 'price_below' as AlertConditionType, value: '' as unknown as number }]

      reset({
        ticker: alert.ticker,
        conditions: conditionsFromAlert,
        condition_logic: alert.condition_logic ?? 'ALL',
        recommended_action: (alert.recommended_action as AlertAction) ?? null,
        priority: alert.priority,
        rationale: alert.rationale,
      })
    } else if (open) {
      reset({
        ticker: '',
        conditions: [{ type: 'price_below', value: '' as unknown as number }],
        condition_logic: 'ALL',
        recommended_action: null,
        priority: 'normal',
        rationale: null,
      })
    }
  }, [open, alert, reset])

  // Auto-suggest action when primary condition type changes (new alerts only)
  const watchedConditions = watch('conditions')
  const watchedAction = watch('recommended_action')
  const primaryConditionType = watchedConditions?.[0]?.type
  useEffect(() => {
    if (isEditing || !primaryConditionType) return
    const suggestedAction = CONDITION_DEFAULT_ACTION[primaryConditionType]
    if (!watchedAction && suggestedAction) {
      setValue('recommended_action', suggestedAction)
    }
  }, [primaryConditionType, isEditing, watchedAction, setValue])

  const onSubmit = async (data: AlertFormData) => {
    const input = {
      ticker: data.ticker.toUpperCase(),
      conditions: data.conditions.map((condition) => ({ type: condition.type, value: condition.value })),
      condition_logic: data.condition_logic,
      recommended_action: data.recommended_action,
      priority: data.priority,
      rationale: data.rationale || null,
    }

    try {
      if (isEditing) {
        await updateAlert.mutateAsync({ id: alert.id, input })
      } else {
        await createAlert.mutateAsync(input)
      }
      onOpenChange(false)
    } catch (error) {
      console.error('Failed to save alert:', error)
    }
  }

  const isPending = createAlert.isPending || updateAlert.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit Alert' : 'New Alert'}</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* Row 1: Ticker + Priority */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="ticker">Ticker <span className="text-destructive">*</span></Label>
              <Input
                id="ticker"
                {...register('ticker', {
                  onChange: (e) => {
                    e.target.value = e.target.value.toUpperCase()
                  },
                })}
                placeholder="TCB"
                maxLength={10}
                disabled={isEditing}
              />
              <FieldError message={errors.ticker?.message} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="priority">Priority</Label>
              <Controller
                name="priority"
                control={control}
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger id="priority" className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {PRIORITIES.map((priority) => (
                        <SelectItem key={priority} value={priority}>
                          {toTitleCase(priority)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
          </div>

          {/* Conditions section */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>
                Conditions <span className="text-destructive">*</span>
                <span className="ml-1.5 text-xs font-normal text-muted-foreground">
                  ({fields.length}/5)
                </span>
              </Label>
              {fields.length >= 2 && (
                <Controller
                  name="condition_logic"
                  control={control}
                  render={({ field }) => (
                    <div className="flex items-center gap-2">
                      <div className="flex items-center gap-1 rounded-md border border-border/60 p-0.5">
                        {(['ALL', 'ANY'] as const).map((val) => (
                          <button
                            key={val}
                            type="button"
                            onClick={() => field.onChange(val)}
                            className={
                              `rounded px-2.5 py-0.5 text-xs font-mono font-medium transition-colors cursor-pointer ` +
                              (field.value === val
                                ? 'bg-primary text-primary-foreground'
                                : 'text-muted-foreground hover:text-foreground')
                            }
                          >
                            {val}
                          </button>
                        ))}
                      </div>
                      <span className="text-[10px] text-muted-foreground">
                        {field.value === 'ALL'
                          ? 'Triggers when all conditions are met'
                          : 'Triggers when any condition is met'}
                      </span>
                    </div>
                  )}
                />
              )}
            </div>

            <div className="space-y-2">
              {fields.map((field, index) => (
                <div
                  key={field.id}
                  className="flex items-center gap-2 rounded-lg border border-border/50 bg-muted/20 p-2.5 animate-in fade-in slide-in-from-top-1 duration-200"
                >
                  <div className="flex-1 grid grid-cols-[1fr_auto] gap-2 items-center min-w-0">
                    <Controller
                      name={`conditions.${index}.type`}
                      control={control}
                      render={({ field: conditionField }) => (
                        <Select value={conditionField.value} onValueChange={conditionField.onChange}>
                          <SelectTrigger className="h-8 text-xs">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {CONDITION_TYPES.map((conditionType) => (
                              <SelectItem key={conditionType.value} value={conditionType.value} className="text-xs">
                                {conditionType.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                    />
                    <Input
                      type="number"
                      step="any"
                      {...register(`conditions.${index}.value`)}
                      placeholder="Value"
                      className="h-8 w-28 text-right font-mono text-xs"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => remove(index)}
                    disabled={fields.length === 1}
                    className="shrink-0 text-muted-foreground hover:text-destructive transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
                    aria-label="Remove condition"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>

            {errors.conditions?.root?.message && (
              <FieldError message={errors.conditions.root.message} />
            )}

            {fields.length < 5 && (
              <button
                type="button"
                onClick={() => append({ type: 'price_below', value: '' as unknown as number })}
                className="w-full flex items-center justify-center gap-1.5 rounded-lg border border-dashed border-border/50 py-2 text-xs text-muted-foreground hover:border-border hover:text-foreground transition-colors cursor-pointer"
              >
                <Plus className="h-3.5 w-3.5" />
                Add condition
              </button>
            )}

            {/* Live preview of what the alert will look like */}
            <ConditionPreview conditions={watchedConditions} />
          </div>

          {/* Recommended action */}
          <div className="space-y-2">
            <Label htmlFor="action">Recommended action</Label>
            <Controller
              name="recommended_action"
              control={control}
              render={({ field }) => (
                <Select
                  value={field.value ?? ''}
                  onValueChange={(value) => field.onChange(value || null)}
                >
                  <SelectTrigger id="action" className="w-full">
                    <SelectValue placeholder="Select..." />
                  </SelectTrigger>
                  <SelectContent>
                    {ACTIONS.map((action) => (
                      <SelectItem key={action} value={action}>
                        {toTitleCase(action)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </div>

          {/* Rationale */}
          <div className="space-y-2">
            <Label htmlFor="rationale">Rationale</Label>
            <Textarea
              id="rationale"
              {...register('rationale')}
              placeholder="Your notes — shown on the alert card"
              rows={2}
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isPending} data-test-id="alert-save-btn">
              {isPending ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
