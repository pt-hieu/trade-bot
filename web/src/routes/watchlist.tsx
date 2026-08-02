import { createFileRoute, useSearch } from '@tanstack/react-router'
import { WatchlistSection } from '../components/watchlist-section'

export const Route = createFileRoute('/watchlist')({
  validateSearch: (search: Record<string, unknown>) => ({
    add: (search.add as string) ?? undefined,
  }),
  component: WatchlistPage,
  ssr: false,
})

function WatchlistPage() {
  const search = useSearch({ from: '/watchlist' })

  return (
    <main className="min-h-[calc(100dvh-77px)] p-6 max-w-7xl mx-auto space-y-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Watchlist</h1>
        <p className="text-muted-foreground text-sm">
          Swing and long-term stock candidates
        </p>
      </header>

      <WatchlistSection addTicker={search.add} />
    </main>
  )
}
