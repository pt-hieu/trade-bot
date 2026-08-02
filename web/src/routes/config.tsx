import { createFileRoute } from '@tanstack/react-router'
import { TradingConfigForm } from '../components/config/trading-config-form'
import { SectorAllocationsForm } from '../components/config/sector-allocations-form'

export const Route = createFileRoute('/config')({
  component: ConfigPage,
  ssr: false,
})

function ConfigPage() {
  return (
    <main className="min-h-[calc(100dvh-77px)] p-6 max-w-5xl mx-auto space-y-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Config</h1>
        <p className="text-muted-foreground text-sm">Trading parameters and risk controls</p>
      </header>

      <TradingConfigForm />
      <SectorAllocationsForm />
    </main>
  )
}
