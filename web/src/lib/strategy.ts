export const STRATEGIES = ['Bounce', 'Trend', 'Breakout', 'Divergence', 'Mean Reversion', 'Momentum', 'Pullback'] as const
export type Strategy = typeof STRATEGIES[number]

export const STRATEGY_DEFINITIONS: Record<Strategy, string> = {
  Bounce: 'Oversold near support — RSI < 40 and price within 5% of support level.',
  Trend: 'Riding an uptrend — price near MA20/MA50 with neutral RSI (35–65).',
  Breakout: 'Breaking above resistance on strong volume — close > resistance with volume ≥ 1.5x average.',
  Divergence: 'Bullish RSI divergence — price at/below swing low but RSI higher than at the low.',
  'Mean Reversion': 'Buying the dip — RSI < 45 near support in a downtrend or sideways market.',
  Momentum: 'Riding strength — RSI > 55, price above MA20, volume above average.',
  Pullback: 'Healthy pullback in uptrend — price between MA20 and MA50 in uptrend/sideways.',
}

/** Progress bar fill color */
export const STRATEGY_BAR_COLOR: Record<string, string> = {
  Bounce: 'bg-emerald-500',
  Trend: 'bg-blue-500',
  Breakout: 'bg-amber-500',
  Divergence: 'bg-purple-500',
  'Mean Reversion': 'bg-cyan-500',
  Momentum: 'bg-orange-500',
  Pullback: 'bg-rose-500',
}

/** Badge styling (transparent bg + colored text) */
export const STRATEGY_BADGE_COLOR: Record<string, string> = {
  Bounce: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  Trend: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  Breakout: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  Divergence: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  'Mean Reversion': 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
  Momentum: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
  Pullback: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
}

/** Active/selected filter chip styling */
export const STRATEGY_ACTIVE_COLOR: Record<Strategy, string> = {
  Bounce: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  Trend: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  Breakout: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  Divergence: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
  'Mean Reversion': 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30',
  Momentum: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  Pullback: 'bg-rose-500/15 text-rose-400 border-rose-500/30',
}

/** Left border accent for trade rows */
export const STRATEGY_BORDER_COLOR: Record<string, string> = {
  Bounce: 'border-l-emerald-500',
  Trend: 'border-l-blue-500',
  Breakout: 'border-l-amber-500',
  Divergence: 'border-l-purple-500',
  'Mean Reversion': 'border-l-cyan-500',
  Momentum: 'border-l-orange-500',
  Pullback: 'border-l-rose-500',
}
