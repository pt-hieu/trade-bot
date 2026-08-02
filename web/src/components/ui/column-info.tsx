import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from './tooltip'
import { Info } from 'lucide-react'
import { cn } from '../../lib/utils'

export function ColumnInfo({ label, tip, className }: { label: string; tip: string; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1', className)}>
      {label}
      <Tooltip>
        <TooltipTrigger asChild>
          <Info className="h-3 w-3 text-muted-foreground/60 cursor-help" />
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[240px]">{tip}</TooltipContent>
      </Tooltip>
    </span>
  )
}
