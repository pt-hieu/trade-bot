import { cn } from '../../../lib/utils'
import { MacroSection } from '../macro-section'
import type { MacroData } from '../../../types/intel'

export function countNegativeSignals(macro: MacroData | null): number {
  if (!macro) return 0
  let count = 0
  if (macro.global_risk_regime === 'ELEVATED' || macro.global_risk_regime === 'CRISIS') count++
  if (macro.dxy_signal === 'STRONG') count++
  if (macro.vix_signal === 'HIGH' || macro.vix_signal === 'EXTREME') count++
  if (macro.usd_vnd_signal === 'FLIGHT') count++
  return count
}

const ESCALATION_STYLES: Record<number, string> = {
  2: 'bg-amber-500/5 border border-amber-500/20 rounded-xl p-3',
  3: 'bg-rose-500/5 border border-rose-500/20 rounded-xl p-3',
}

interface MacroEscalationProps {
  macro: MacroData
}

export function MacroEscalation({ macro }: MacroEscalationProps) {
  const negativeCount = countNegativeSignals(macro)
  const wrapperStyle = negativeCount >= 3
    ? ESCALATION_STYLES[3]
    : negativeCount === 2
      ? ESCALATION_STYLES[2]
      : null

  if (!wrapperStyle) {
    return <MacroSection macro={macro} />
  }

  return (
    <div className={cn(wrapperStyle)}>
      <MacroSection macro={macro} />
    </div>
  )
}
