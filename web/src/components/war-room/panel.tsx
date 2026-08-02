import { Link } from '@tanstack/react-router'
import { AlertCircle } from 'lucide-react'
import { Badge } from '../ui/badge'
import { Skeleton } from '../ui/skeleton'

interface PanelHeaderProps {
  title: string
  href: string
  linkText: string
  count?: number
  children?: React.ReactNode
}

export function PanelHeader({ title, href, linkText, count, children }: PanelHeaderProps) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/30">
      <div className="flex items-center gap-2">
        <h3 className="text-[10px] font-medium tracking-widest text-muted-foreground uppercase">
          {title}
        </h3>
        {count != null && count > 0 && (
          <Badge variant="secondary" className="h-4 px-1.5 text-[10px] font-mono">
            {count}
          </Badge>
        )}
      </div>
      <div className="flex items-center gap-2">
        {children}
        <Link
          to={href}
          className="text-[10px] text-muted-foreground hover:text-foreground transition-colors"
        >
          {linkText}
        </Link>
      </div>
    </div>
  )
}

interface PanelErrorProps {
  message: string
  onRetry: () => void
}

export function PanelError({ message, onRetry }: PanelErrorProps) {
  return (
    <div className="flex items-center gap-2 px-4 py-3 text-xs text-muted-foreground">
      <AlertCircle className="h-3 w-3 shrink-0" />
      <span>{message}</span>
      <button onClick={onRetry} className="underline cursor-pointer">
        Retry
      </button>
    </div>
  )
}

interface PanelSkeletonProps {
  rows?: number
  children: React.ReactNode
}

export function PanelSkeleton({ rows = 3, children }: PanelSkeletonProps) {
  return (
    <>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i}>{children}</div>
      ))}
    </>
  )
}

export function SkeletonRow({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={className}>{children}</div>
}

export { Skeleton }
