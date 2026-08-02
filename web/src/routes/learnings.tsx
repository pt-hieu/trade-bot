import { createFileRoute } from '@tanstack/react-router'
import { useMemo, type ReactNode } from 'react'
import { useLearnings } from '../hooks/use-learnings'
import {
  HealthVerdictBanner,
  computeHealthVerdict,
  SummaryStats,
  PatternsCard,
  NeedsAttention,
  DiagnosticCard,
  CalibrationContent,
  calibrationSubtitle,
  MiddayCard,
  TradingModeContent,
  tradingModeSubtitle,
  RotationContent,
  rotationSubtitle,
  TickerAccuracyContent,
  tickerAccuracySubtitle,
  MacroContent,
  macroSubtitle,
  StrategyContent,
  strategySubtitle,
  SectionHeader,
} from '../components/learnings'
import { ErrorState } from '../components/ui/error-state'
import { Skeleton } from '../components/ui/skeleton'
import type { EnrichedLearningsData } from '../types/learnings'
import { Sparkles, Search, Crosshair, Swords, RefreshCw, ShieldCheck, Globe, Target } from 'lucide-react'

export const Route = createFileRoute('/learnings')({
  component: LearningsPage,
  ssr: false,
})

function PageShell({ children }: { children: ReactNode }) {
  return (
    <main className="min-h-[calc(100dvh-77px)] p-6 max-w-7xl mx-auto space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Learnings</h1>
        <p className="text-muted-foreground text-sm">
          Cumulative patterns from daily retrospectives
        </p>
      </header>
      {children}
    </main>
  )
}

function LearningsSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-14 w-full" />
      <div className="flex gap-3">
        {[...Array(5)].map((_, index) => (
          <Skeleton key={index} className="h-16 flex-1" />
        ))}
      </div>
      <Skeleton className="h-8 w-64" />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Skeleton className="h-48" />
        <Skeleton className="h-48" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Skeleton className="h-12" />
        <Skeleton className="h-12" />
        <Skeleton className="h-12" />
        <Skeleton className="h-12" />
      </div>
    </div>
  )
}

function LearningsPage() {
  const { data: dataRaw, isLoading, error, refetch } = useLearnings()
  const data = dataRaw as EnrichedLearningsData | undefined

  const healthVerdict = useMemo(() => {
    if (!data) return null
    return computeHealthVerdict(data)
  }, [data])

  const healthMap = useMemo(() => {
    if (!healthVerdict) return new Map<string, 'green' | 'amber' | 'red'>()
    return new Map(healthVerdict.subsystems.map((entry) => [entry.name, entry.status]))
  }, [healthVerdict])

  if (isLoading) {
    return (
      <PageShell>
        <LearningsSkeleton />
      </PageShell>
    )
  }

  if (error) {
    return (
      <PageShell>
        <ErrorState
          description="Could not load learning patterns. Patterns emerge after daily retrospectives are analyzed."
          retry={refetch}
        />
      </PageShell>
    )
  }

  if (!data) {
    return (
      <PageShell>
        <div className="text-center py-12 space-y-1">
          <p className="text-muted-foreground text-sm">No learning patterns yet.</p>
          <p className="text-muted-foreground/50 text-xs">
            Patterns emerge after multiple daily retrospectives have been analyzed.
          </p>
        </div>
      </PageShell>
    )
  }

  return (
    <PageShell>
      {healthVerdict && <HealthVerdictBanner verdict={healthVerdict} />}

      <SummaryStats summary={data.summary} />

      <NeedsAttention
        losingPatterns={data.losing_patterns}
        tradingRules={data.trading_rules}
      />

      {(data.winning_patterns.length > 0 ||
        (data.midday && Number(data.midday.average_improvement ?? 0) > 0)) && (
        <section className="space-y-3">
          <SectionHeader icon={Sparkles} title="Strong signals" colorClass="text-emerald-400" />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <PatternsCard title="Winning Patterns" patterns={data.winning_patterns} type="winning" />
            <MiddayCard data={data.midday} />
          </div>
        </section>
      )}

      <section className="space-y-3">
        <SectionHeader icon={Search} title="Diagnostics" colorClass="text-muted-foreground" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 items-start">
          {data.calibration && (
            <DiagnosticCard
              healthStatus={healthMap.get('calibration')}
              icon={Crosshair}
              title="Calibration"
              subtitle={calibrationSubtitle(data.calibration)}
            >
              <CalibrationContent data={data.calibration} />
            </DiagnosticCard>
          )}
          <DiagnosticCard
            healthStatus={healthMap.get('strategy')}
            icon={Swords}
            title="Strategy win rates"
            subtitle={strategySubtitle(data.strategy_insights)}
          >
            <StrategyContent data={data.strategy_insights} />
          </DiagnosticCard>
          {data.rotation && (
            <DiagnosticCard
              healthStatus={healthMap.get('rotation')}
              icon={RefreshCw}
              title="Sector rotation"
              subtitle={rotationSubtitle(data.rotation)}
            >
              <RotationContent data={data.rotation} sectorInsights={data.sector_insights} />
            </DiagnosticCard>
          )}
          {data.ticker_insights.length > 0 && (
            <DiagnosticCard
              icon={Target}
              title="Ticker signal accuracy"
              subtitle={tickerAccuracySubtitle(data.ticker_insights)}
            >
              <TickerAccuracyContent insights={data.ticker_insights} />
            </DiagnosticCard>
          )}
          {data.trading_mode && (
            <DiagnosticCard
              healthStatus={healthMap.get('trading-mode')}
              icon={ShieldCheck}
              title="Trading mode compliance"
              subtitle={tradingModeSubtitle(data.trading_mode)}
            >
              <TradingModeContent data={data.trading_mode} />
            </DiagnosticCard>
          )}
        </div>
        {data.macro && (
          <DiagnosticCard
            healthStatus={healthMap.get('macro')}
            icon={Globe}
            title="Macro regime accuracy"
            subtitle={macroSubtitle(data.macro)}
          >
            <MacroContent data={data.macro} />
          </DiagnosticCard>
        )}
      </section>
    </PageShell>
  )
}
