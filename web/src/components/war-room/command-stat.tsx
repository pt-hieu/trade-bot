import { cn } from '../../lib/utils'
import { Card } from '../ui/card'
import { Skeleton } from '../ui/skeleton'
import type { VariantProps } from 'class-variance-authority'
import type { cardVariants } from '../ui/card'

interface CommandStatProps {
  label: string
  value: string | null
  subtitle?: string
  gradient?: VariantProps<typeof cardVariants>['gradient']
  onClick?: () => void
  isLoading?: boolean
  'data-test-id'?: string
}

export function CommandStat({
  label,
  value,
  subtitle,
  gradient = 'none',
  onClick,
  isLoading,
  'data-test-id': testId,
}: CommandStatProps) {
  if (isLoading) {
    return (
      <Card className="border-border/50 py-3 px-4 gap-2">
        <Skeleton className="h-3 w-16" />
        <Skeleton className="h-7 w-24 mt-1" />
        <Skeleton className="h-3 w-20" />
      </Card>
    )
  }

  return (
    <Card
      gradient={gradient}
      className={cn(
        'border-border/50 py-3 px-4 gap-1.5',
        onClick && 'cursor-pointer hover:border-border transition-colors'
      )}
      onClick={onClick}
      data-test-id={testId}
    >
      <p className="text-[10px] font-medium tracking-widest text-muted-foreground uppercase">
        {label}
      </p>
      <p className="font-mono text-2xl font-semibold tabular-nums leading-none">
        {value ?? '—'}
      </p>
      {subtitle && (
        <p className="text-xs text-muted-foreground font-mono tabular-nums">
          {subtitle}
        </p>
      )}
    </Card>
  )
}
