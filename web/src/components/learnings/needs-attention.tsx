import { AlertTriangle } from 'lucide-react'
import type { LearningPattern } from '../../types/intel'
import type { TradingRule } from '../../types/learnings'
import { PatternsCard } from './patterns-card'
import { RulesCard } from './rules-card'
import { SectionHeader } from './section-header'

interface NeedsAttentionProps {
  losingPatterns: LearningPattern[]
  tradingRules: TradingRule[]
}

export function NeedsAttention({ losingPatterns, tradingRules }: NeedsAttentionProps) {
  const hasPatterns = losingPatterns.length > 0
  const hasRules = tradingRules.length > 0
  if (!hasPatterns && !hasRules) return null

  const fewLosingPatterns = losingPatterns.length <= 2
  const onlyRules = !hasPatterns && hasRules
  const onlyPatterns = hasPatterns && !hasRules

  return (
    <section className="space-y-3">
      <SectionHeader icon={AlertTriangle} title="Needs attention" colorClass="text-amber-400" />
      <div className="rounded-xl bg-rose-500/[0.03] border border-rose-500/10 p-4">
        {onlyRules ? (
          <RulesCard data={tradingRules} />
        ) : onlyPatterns ? (
          <PatternsCard title="Losing Patterns" patterns={losingPatterns} type="losing" />
        ) : (
          <div
            className={`grid grid-cols-1 gap-4 ${
              fewLosingPatterns ? 'lg:grid-cols-[1fr_2fr]' : 'lg:grid-cols-2'
            }`}
          >
            <PatternsCard title="Losing Patterns" patterns={losingPatterns} type="losing" />
            <RulesCard data={tradingRules} />
          </div>
        )}
      </div>
    </section>
  )
}
