import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { TooltipProvider } from '../../ui/tooltip'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetBody,
  SheetDescription,
} from '../../ui/sheet'
import { SectionTable } from '../recommendations/tables'
import { cn } from '../../../lib/utils'
import type { Recommendation } from '../../../types/intel'
import type { SectionKey } from '../recommendations/shared'

interface CollapsibleSectionProps {
  label: string
  recs: Recommendation[]
  section?: SectionKey
}

export function CollapsibleSection({ label, recs, section = 'OTHER' }: CollapsibleSectionProps) {
  const [isOpen, setIsOpen] = useState(false)

  if (recs.length === 0) return null

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="inline-flex items-center gap-1.5 text-left cursor-pointer hover:bg-muted/30 rounded-md px-2 py-0.5 transition-colors"
      >
        <span className="text-xs text-muted-foreground">
          <span className="font-mono font-medium text-zinc-400">{recs.length}</span>
          {' '}{label}
        </span>
        <ChevronRight className="h-3 w-3 text-zinc-600 shrink-0" />
      </button>

      <Sheet open={isOpen} onOpenChange={setIsOpen}>
        <SheetContent side="right" className={cn(
          'max-w-lg',
          section === 'TOP_PICKS' && 'max-w-2xl',
        )}>
          <SheetHeader>
            <SheetTitle className="capitalize">{label}</SheetTitle>
            <SheetDescription>
              {recs.length} ticker{recs.length !== 1 ? 's' : ''}
            </SheetDescription>
          </SheetHeader>
          <SheetBody className="overflow-x-hidden">
            <TooltipProvider>
              <div className="w-full [&_table]:table-fixed [&_table]:w-full">
                <SectionTable section={section} recs={recs} />
              </div>
            </TooltipProvider>
          </SheetBody>
        </SheetContent>
      </Sheet>
    </>
  )
}
