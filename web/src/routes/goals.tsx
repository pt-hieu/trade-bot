import { createFileRoute } from '@tanstack/react-router'
import { GoalsSection } from '../components/goals-section'

export const Route = createFileRoute('/goals')({
  component: GoalsPage,
  ssr: false,
})

function GoalsPage() {
  return (
    <main className="min-h-[calc(100dvh-77px)] p-6 max-w-7xl mx-auto space-y-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Goals</h1>
        <p className="text-muted-foreground text-sm">
          Monthly trading targets
        </p>
      </header>

      <GoalsSection />
    </main>
  )
}
