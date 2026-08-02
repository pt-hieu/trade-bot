import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { cn } from '../../../lib/utils'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '../../ui/collapsible'
import { MacroEscalation, countNegativeSignals } from './macro-escalation'
import { ForeignFlowSection } from '../foreign-flow-section'
import { RotationSection } from '../rotation-section'
import type { MacroData, ForeignFlowData, RotationData } from '../../../types/intel'

// ── Section ─────────────────────────────────────────────────────────────────

interface MarketContextSectionProps {
  macro: MacroData | null
  foreignFlow: ForeignFlowData | null
  rotation: RotationData | null
  portfolioTickers: Set<string>
}

export function MarketContextSection({
  macro,
  foreignFlow,
  rotation,
  portfolioTickers,
}: MarketContextSectionProps) {
  const hasMacro = macro != null
  const hasFlow = foreignFlow != null
  const hasRotation = rotation != null
  const sectionCount = [hasMacro, hasFlow, hasRotation].filter(Boolean).length

  if (sectionCount === 0) return null

  // Auto-open when macro has escalation signals
  const escalationSignals = countNegativeSignals(macro)
  const defaultOpen = escalationSignals >= 2

  const [isOpen, setIsOpen] = useState(defaultOpen)

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className="space-y-4">
        <CollapsibleTrigger className="flex items-center gap-2 group cursor-pointer">
          <ChevronRight className="h-3 w-3 text-muted-foreground transition-transform group-data-[state=open]:rotate-90" />
          <h3 className="text-xs font-medium tracking-widest text-muted-foreground uppercase">
            Market Context
          </h3>
          <span className="text-xs text-zinc-500">
            — {sectionCount} section{sectionCount !== 1 ? 's' : ''}
          </span>
          {escalationSignals >= 2 && (
            <span className={cn(
              'h-1.5 w-1.5 rounded-full shrink-0',
              escalationSignals >= 3 ? 'bg-rose-400 animate-pulse' : 'bg-amber-400',
            )} />
          )}
        </CollapsibleTrigger>

        <CollapsibleContent>
          <div className="space-y-6">
            {hasMacro && <MacroEscalation macro={macro} />}
            {hasFlow && (
              <ForeignFlowSection flow={foreignFlow} portfolioTickers={portfolioTickers} />
            )}
            {hasRotation && <RotationSection rotation={rotation} />}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  )
}
