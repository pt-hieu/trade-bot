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
import { useCreateGoal, useUpdateGoal } from '../hooks/use-goals'
import { formatDateForInput as formatDate } from '../lib/date'
import type { Goal, GoalInput } from '../types/index'

interface GoalDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  goal?: Goal
}

const STATUSES = ['Active', 'Achieved', 'Failed', 'Paused', 'Tracking'] as const
const GOAL_TYPES = ['Monthly', 'Quarterly', 'Yearly', 'Custom'] as const

const goalSchema = z
  .object({
    name: z.string().min(1, 'Required').max(100, 'Max 100 chars'),
    target_vnd: z.coerce.number().min(1, 'Must be > 0'),
    realized_vnd: z.coerce.number(),
    start_date: z.string().min(1, 'Required'),
    deadline: z.string().min(1, 'Required'),
    status: z.enum(STATUSES),
    goal_type: z.enum(GOAL_TYPES),
    notes: z.string().nullable(),
  })
  .refine((data) => new Date(data.start_date) < new Date(data.deadline), {
    message: 'Start date must be before deadline',
    path: ['deadline'],
  })

type GoalFormData = z.infer<typeof goalSchema>

import { FieldError } from './ui/field-error'

export function GoalDialog({ open, onOpenChange, goal }: GoalDialogProps) {
  const createGoal = useCreateGoal()
  const updateGoal = useUpdateGoal()
  const isEditing = !!goal

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<GoalFormData>({
    resolver: zodResolver(goalSchema),
    defaultValues: {
      name: '',
      target_vnd: '' as unknown as number,
      realized_vnd: 0,
      start_date: new Date().toISOString().split('T')[0],
      deadline: '',
      status: 'Active',
      goal_type: 'Monthly',
      notes: null,
    },
  })

  const formatDateForInput = (date: string | Date | null): string => formatDate(date)

  useEffect(() => {
    if (open && goal) {
      reset({
        name: goal.name,
        target_vnd: goal.target_vnd,
        realized_vnd: goal.realized_vnd,
        start_date: formatDateForInput(goal.start_date),
        deadline: formatDateForInput(goal.deadline),
        status: goal.status ?? 'Active',
        goal_type: goal.goal_type ?? 'Monthly',
        notes: goal.notes,
      })
    } else if (open) {
      reset({
        name: '',
        target_vnd: '' as unknown as number,
        realized_vnd: 0,
        start_date: new Date().toISOString().split('T')[0],
        deadline: '',
        status: 'Active',
        goal_type: 'Monthly',
        notes: null,
      })
    }
  }, [open, goal, reset])

  const onSubmit = async (data: GoalFormData) => {
    const input: GoalInput = {
      name: data.name,
      target_vnd: data.target_vnd,
      realized_vnd: data.realized_vnd,
      start_date: data.start_date,
      deadline: data.deadline,
      status: data.status,
      goal_type: data.goal_type,
      notes: data.notes || null,
    }

    try {
      if (isEditing) {
        await updateGoal.mutateAsync({ id: goal.id, input })
      } else {
        await createGoal.mutateAsync(input)
      }
      onOpenChange(false)
    } catch (error) {
      console.error('Failed to save goal:', error)
    }
  }

  const isPending = createGoal.isPending || updateGoal.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit Goal' : 'New Goal'}</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Name <span className="text-destructive">*</span></Label>
            <Input
              id="name"
              {...register('name')}
              placeholder="February 2026"
              maxLength={100}
            />
            <FieldError message={errors.name?.message} />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="goalType">Type</Label>
              <Controller
                name="goal_type"
                control={control}
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger id="goalType" className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {GOAL_TYPES.map((t) => (
                        <SelectItem key={t} value={t}>
                          {t}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
              <FieldError message={errors.goal_type?.message} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="status">Status</Label>
              <Controller
                name="status"
                control={control}
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger id="status" className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {STATUSES.map((s) => (
                        <SelectItem key={s} value={s}>
                          {s}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
              <FieldError message={errors.status?.message} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="targetVnd">Target (VND) <span className="text-destructive">*</span></Label>
              <Input
                id="targetVnd"
                type="number"
                {...register('target_vnd')}
                placeholder="5000000"
              />
              <FieldError message={errors.target_vnd?.message} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="realizedVnd">Realized (VND)</Label>
              <Input
                id="realizedVnd"
                type="number"
                {...register('realized_vnd')}
                placeholder="0"
              />
              <FieldError message={errors.realized_vnd?.message} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="startDate">Start Date <span className="text-destructive">*</span></Label>
              <Input id="startDate" type="date" {...register('start_date')} />
              <FieldError message={errors.start_date?.message} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="deadline">Deadline <span className="text-destructive">*</span></Label>
              <Input id="deadline" type="date" {...register('deadline')} />
              <FieldError message={errors.deadline?.message} />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="notes">Notes</Label>
            <Textarea
              id="notes"
              {...register('notes')}
              placeholder="Optional notes..."
              rows={2}
            />
            <FieldError message={errors.notes?.message} />
          </div>

          <div className="flex justify-end gap-2 pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isPending}
            >
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
