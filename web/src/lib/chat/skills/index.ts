/**
 * Skill registry — maps skill names to domain expertise text.
 * Used by the load_skill broker tool to return expertise as tool output.
 */
import { PORTFOLIO_SKILL } from './portfolio'
import { MARKET_SKILL } from './market'
import { WATCHLIST_SKILL } from './watchlist'
import { PIPELINE_SKILL } from './pipeline'

export const SKILL_NAMES = ['portfolio', 'market', 'watchlist', 'pipeline'] as const
export type SkillName = (typeof SKILL_NAMES)[number]

export const SKILL_REGISTRY: Record<SkillName, string> = {
  portfolio: PORTFOLIO_SKILL,
  market: MARKET_SKILL,
  watchlist: WATCHLIST_SKILL,
  pipeline: PIPELINE_SKILL,
}
