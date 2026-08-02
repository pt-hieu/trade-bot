import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from './tooltip'
import { Info } from 'lucide-react'

export function CardLabel({ label, tip }: { label: string; tip: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="text-[10px] font-medium tracking-widest text-muted-foreground uppercase">{label}</span>
      <Tooltip>
        <TooltipTrigger asChild>
          <Info className="h-3 w-3 text-muted-foreground/60 cursor-help" />
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[240px]">{tip}</TooltipContent>
      </Tooltip>
    </span>
  )
}
