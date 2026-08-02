import { useState, type ReactNode, type ComponentType } from 'react'
import { Card } from '../ui/card'
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from '../ui/collapsible'
import { ChevronRight, type LucideProps } from 'lucide-react'
import { HealthDot } from './health-verdict'
import type { HealthStatus } from '../../types/learnings'

interface DiagnosticCardProps {
  healthStatus?: HealthStatus
  icon: ComponentType<LucideProps>
  title: string
  subtitle?: string
  defaultOpen?: boolean
  children: ReactNode
}

export function DiagnosticCard({
  healthStatus,
  icon,
  title,
  subtitle,
  defaultOpen,
  children,
}: DiagnosticCardProps) {
  const Icon = icon
  const shouldAutoExpand =
    defaultOpen ?? (healthStatus === 'red' || healthStatus === 'amber')
  const [isOpen, setIsOpen] = useState(shouldAutoExpand)

  return (
    <Card className="border-border/50 p-0 overflow-hidden">
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <CollapsibleTrigger className="w-full text-left cursor-pointer">
          <div className="flex items-center gap-2 px-4 py-3 hover:bg-muted/30 transition-colors">
            {healthStatus && <HealthDot status={healthStatus} />}
            <Icon className="h-4 w-4 text-muted-foreground/60 shrink-0" />
            <h3 className="text-sm font-medium flex-1">{title}</h3>
            {subtitle && (
              <span className="text-[10px] font-mono text-muted-foreground mr-2">
                {subtitle}
              </span>
            )}
            <ChevronRight
              className={`h-4 w-4 text-muted-foreground/40 transition-transform duration-200 ${
                isOpen ? 'rotate-90' : ''
              }`}
            />
          </div>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="px-4 pb-4 pt-1">{children}</div>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  )
}
