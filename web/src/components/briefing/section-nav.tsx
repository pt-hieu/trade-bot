import { Link, useLocation, useSearch } from '@tanstack/react-router'
import { cn } from '../../lib/utils'

const PILL_ITEMS = [
  { href: '/briefing', label: 'Morning' },
  { href: '/briefing/midday', label: 'Midday' },
] as const

export function BriefingPillToggle() {
  const { pathname } = useLocation()
  const search = useSearch({ strict: false }) as { date?: string }
  const dateParam = search?.date

  return (
    <div className="flex items-center gap-0.5 rounded-full bg-muted/50 p-0.5">
      {PILL_ITEMS.map((item) => {
        const isActive =
          item.href === '/briefing'
            ? pathname === '/briefing' || pathname === '/briefing/'
            : pathname.startsWith(item.href)
        const to = dateParam ? `${item.href}?date=${dateParam}` : item.href

        return (
          <Link
            key={item.href}
            to={to}
            className={cn(
              'px-3 py-1 rounded-full text-xs font-medium transition-colors cursor-pointer',
              isActive
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {item.label}
          </Link>
        )
      })}
    </div>
  )
}
