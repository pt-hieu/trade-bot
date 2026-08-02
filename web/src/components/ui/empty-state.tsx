import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button } from './button'

interface EmptyStateProps {
  icon?: LucideIcon
  illustration?: ReactNode
  title: string
  description: string
  action?: {
    label: string
    onClick: () => void
  }
}

export function EmptyState({ icon: Icon, illustration, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      {illustration ? (
        <div className="mb-6">{illustration}</div>
      ) : Icon ? (
        <Icon className="h-12 w-12 text-muted-foreground/50 mb-4" />
      ) : null}
      <h3 className="font-medium text-lg mb-1">{title}</h3>
      <p className="text-muted-foreground text-sm max-w-sm mb-4">{description}</p>
      {action && (
        <Button onClick={action.onClick}>{action.label}</Button>
      )}
    </div>
  )
}
