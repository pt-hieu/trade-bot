import { useEffect, useRef } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from './ui/dialog'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Label } from './ui/label'
import { Spinner } from './ui/spinner'
import { useUpdateCash } from '../hooks/use-portfolio'
import { formatVND } from '../lib/utils'

interface CashDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  currentBalance: number
}

const cashSchema = z.object({
  amount: z.coerce.number().min(0, 'Must be >= 0'),
})

type CashFormData = z.infer<typeof cashSchema>

export function CashDialog({
  open,
  onOpenChange,
  currentBalance,
}: CashDialogProps) {
  const updateCash = useUpdateCash()
  const inputRef = useRef<HTMLInputElement>(null)

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<CashFormData>({
    resolver: zodResolver(cashSchema),
    defaultValues: {
      amount: currentBalance,
    },
  })

  useEffect(() => {
    if (open) {
      reset({ amount: currentBalance })
      setTimeout(() => inputRef.current?.select(), 50)
    }
  }, [open, currentBalance, reset])

  const amount = watch('amount') || 0
  const delta = amount - currentBalance

  const onSubmit = async (data: CashFormData) => {
    try {
      await updateCash.mutateAsync(data.amount)
      onOpenChange(false)
    } catch (error) {
      console.error('Failed to update cash:', error)
    }
  }

  const { ref: formRef, ...registerProps } = register('amount')

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm" data-test-id="cash-dialog">
        <DialogHeader>
          <DialogTitle className="font-mono tracking-tight">
            Adjust Cash
          </DialogTitle>
          <DialogDescription className="text-xs font-mono tabular-nums">
            Current: {formatVND(currentBalance)}
            {delta !== 0 && (
              <span
                className={`ml-2 ${
                  delta > 0 ? 'text-emerald-500' : 'text-rose-500'
                }`}
                data-test-id="cash-delta"
              >
                ({delta > 0 ? '+' : ''}{formatVND(delta)})
              </span>
            )}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label
              htmlFor="amount"
              className="text-[10px] uppercase tracking-widest text-muted-foreground"
            >
              New Balance
            </Label>
            <div className="relative">
              <Input
                id="amount"
                type="number"
                {...registerProps}
                ref={(e) => {
                  formRef(e)
                  inputRef.current = e
                }}
                className="font-mono text-2xl h-14 pr-16 tabular-nums tracking-tight"
                placeholder="0"
                data-test-id="cash-input"
              />
              <span className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground text-sm font-medium">
                VND
              </span>
            </div>
            {errors.amount && (
              <p className="text-xs text-destructive">{errors.amount.message}</p>
            )}
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={updateCash.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={updateCash.isPending || delta === 0}
              data-test-id="cash-submit"
            >
              {updateCash.isPending ? (
                <>
                  <Spinner /> Updating...
                </>
              ) : (
                'Update'
              )}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
