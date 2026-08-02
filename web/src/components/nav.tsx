import { Link, useLocation } from '@tanstack/react-router'
import {
  ChevronDown,
  Home,
  FileText,
  TrendingUp,
  Newspaper,
  BarChart3,
  Settings,
  Bell,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '../lib/utils'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from './ui/dropdown-menu'
import { useAlertBadgeCount } from '../hooks/use-alerts'

interface NavLink {
  href: string
  label: string
  icon: LucideIcon
}

interface NavDropdownItem {
  href: string
  label: string
}

interface NavGroup {
  label: string
  icon: LucideIcon
  items: NavDropdownItem[]
}

type NavEntry = NavLink | NavGroup

function isGroup(entry: NavEntry): entry is NavGroup {
  return 'items' in entry
}

// Attention → Action → Reflection
// Alerts + System are right-anchored, outside this array
const NAV_ENTRIES: NavEntry[] = [
  { href: '/', label: 'Home', icon: Home },
  {
    label: 'Briefing',
    icon: FileText,
    items: [
      { href: '/briefing', label: 'Morning' },
      { href: '/briefing/midday', label: 'Midday' },
    ],
  },
  {
    label: 'Trading',
    icon: TrendingUp,
    items: [
      { href: '/portfolio', label: 'Portfolio' },
      { href: '/trades', label: 'Trades' },
      { href: '/watchlist', label: 'Watchlist' },
    ],
  },
  { href: '/newsroom', label: 'Newsroom', icon: Newspaper },
  {
    label: 'Review',
    icon: BarChart3,
    items: [
      { href: '/learnings', label: 'Learnings' },
      { href: '/goals', label: 'Goals' },
    ],
  },
]

export function Nav() {
  const pathname = useLocation().pathname
  const { data: alertCount } = useAlertBadgeCount()
  const unactedCount = alertCount ?? 0

  return (
    <nav className="border-b border-border">
      <div className="max-w-7xl mx-auto px-6">
        <div className="flex items-center justify-between h-[77px]">
          <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight">
            <svg width="20" height="20" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect width="32" height="32" rx="7" fill="#141414"/>
              <defs>
                <linearGradient id="wave" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#a855f7"/>
                  <stop offset="100%" stopColor="#2db4cc"/>
                </linearGradient>
              </defs>
              <path d="M5 20 C8 26, 12 8, 16 16 C20 24, 24 6, 27 11" stroke="url(#wave)" strokeWidth="2.5" fill="none" strokeLinecap="round"/>
              <circle cx="27" cy="11" r="2.5" fill="#2db4cc" opacity="0.9"/>
            </svg>
            Swingy
          </Link>

          <div className="flex items-center gap-1">
            {NAV_ENTRIES.map((entry) => {
              if (!isGroup(entry)) {
                const isActive = entry.href === '/'
                  ? pathname === '/'
                  : pathname.startsWith(entry.href)
                const Icon = entry.icon
                return (
                  <Link
                    key={entry.href}
                    to={entry.href}
                    className={cn(
                      'inline-flex items-center gap-1.5 text-sm transition-colors px-3 py-1.5 rounded-md',
                      isActive
                        ? 'text-foreground font-medium'
                        : 'text-muted-foreground hover:text-foreground'
                    )}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {entry.label}
                  </Link>
                )
              }

              const isGroupActive = entry.items.some((item) => pathname.startsWith(item.href))
              const Icon = entry.icon
              return (
                <DropdownMenu key={entry.label}>
                  <DropdownMenuTrigger asChild>
                    <button
                      className={cn(
                        'inline-flex items-center gap-1.5 text-sm transition-colors px-3 py-1.5 rounded-md cursor-pointer',
                        isGroupActive
                          ? 'text-foreground font-medium'
                          : 'text-muted-foreground hover:text-foreground'
                      )}
                    >
                      <Icon className="h-3.5 w-3.5" />
                      {entry.label}
                      <ChevronDown className="h-3 w-3 opacity-60" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="center" className="min-w-[120px]">
                    {entry.items.map((item) => {
                      const isActive = pathname.startsWith(item.href)
                      return (
                        <DropdownMenuItem key={item.href} asChild>
                          <Link
                            to={item.href}
                            className={cn(
                              'cursor-pointer',
                              isActive && 'text-foreground font-medium'
                            )}
                          >
                            {item.label}
                          </Link>
                        </DropdownMenuItem>
                      )
                    })}
                  </DropdownMenuContent>
                </DropdownMenu>
              )
            })}
          </div>

          <div className="flex items-center gap-1">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  className={cn(
                    'inline-flex items-center justify-center text-sm transition-colors p-2 rounded-md cursor-pointer',
                    (pathname.startsWith('/agents') || pathname.startsWith('/config'))
                      ? 'text-foreground'
                      : 'text-muted-foreground hover:text-foreground'
                  )}
                >
                  <Settings className="h-4 w-4" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="min-w-[120px]">
                <DropdownMenuItem asChild>
                  <Link
                    to="/agents"
                    className={cn('cursor-pointer', pathname.startsWith('/agents') && 'text-foreground font-medium')}
                  >
                    Agents
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link
                    to="/config"
                    className={cn('cursor-pointer', pathname.startsWith('/config') && 'text-foreground font-medium')}
                  >
                    Config
                  </Link>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <Link
              to="/alerts"
              className={cn(
                'relative inline-flex items-center justify-center p-2 rounded-md transition-colors cursor-pointer',
                pathname.startsWith('/alerts')
                  ? 'text-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <Bell className="h-4 w-4" />
              {unactedCount > 0 && (
                <span className="absolute -top-0.5 -right-0.5 flex items-center justify-center min-w-[16px] h-4 px-1 text-[10px] font-semibold tabular-nums rounded-full bg-rose-500 text-white">
                  {unactedCount > 99 ? '99+' : unactedCount}
                </span>
              )}
            </Link>
          </div>
        </div>
      </div>
    </nav>
  )
}
