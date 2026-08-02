/**
 * Agent graph data — fully static, no DB dependency.
 *
 * Agent config lives in YAML files (scripts/agents/configs/).
 * This module provides the pipeline topology for the graph visualization.
 */

import type { StaticAgent, AgentGraphData } from '../../types/agents'

/** All known agents with display metadata. Model IDs are approximate — YAML is source of truth. */
const AGENTS: Record<string, Omit<StaticAgent, 'agent_key'>> = {
  market_level: { agent_name: 'Market Level', description: 'Classifies VN market regime', model_id: 'moonshotai/Kimi-K2.5' },
  sector: { agent_name: 'Sector Aggregator', description: 'Aggregates sector analysis', model_id: 'moonshotai/Kimi-K2.5' },
  longterm: { agent_name: 'Long-Term Scanner', description: 'Analyzes long-term watchlist', model_id: 'moonshotai/Kimi-K2.5' },
  positions_technical: { agent_name: 'Positions Technical', description: 'Technical analysis of holdings', model_id: 'moonshotai/Kimi-K2.5' },
  positions_value: { agent_name: 'Positions Value', description: 'Fundamental analysis of holdings', model_id: 'moonshotai/Kimi-K2.5' },
  positions_thesis: { agent_name: 'Positions Thesis', description: 'Thesis analysis of holdings', model_id: 'moonshotai/Kimi-K2.5' },
  positions_aggregator: { agent_name: 'Positions Aggregator', description: 'Aggregates position analyst reports', model_id: 'moonshotai/Kimi-K2.5' },
  positions_pev_alert: { agent_name: 'PEV Alert', description: 'Price-entry-value alert detection', model_id: 'moonshotai/Kimi-K2.5' },
  positions_pev_verifier: { agent_name: 'PEV Verifier', description: 'Verifies PEV alerts', model_id: 'moonshotai/Kimi-K2.5' },
  trading_mode: { agent_name: 'Trading Mode', description: 'Determines trading mode', model_id: 'moonshotai/Kimi-K2.5' },
  position_strategist: { agent_name: 'Position Strategist', description: 'Position guidance for holdings', model_id: 'moonshotai/Kimi-K2.5' },
  entry_strategist: { agent_name: 'Entry Strategist', description: 'Entry strategy for new picks', model_id: 'moonshotai/Kimi-K2.5' },
  synthesis: { agent_name: 'Synthesis', description: 'Orchestrates sub-writers', model_id: 'moonshotai/Kimi-K2.5' },
  synthesis_holdings: { agent_name: 'Holdings Writer', description: 'Writes MY HOLDINGS section', model_id: 'moonshotai/Kimi-K2.5' },
  synthesis_picks: { agent_name: 'Picks Writer', description: 'Writes TOP PICKS section', model_id: 'moonshotai/Kimi-K2.5' },
  critic: { agent_name: 'Morning Critic', description: 'Reviews morning brief for errors', model_id: 'moonshotai/Kimi-K2.5' },
  refiner: { agent_name: 'Refiner', description: 'Refines brief based on critic feedback', model_id: 'moonshotai/Kimi-K2.5' },
  retro_evaluator: { agent_name: 'Retro Evaluator', description: 'Evaluates past recommendations', model_id: 'moonshotai/Kimi-K2.5' },
  retro_eval_critic: { agent_name: 'Eval Critic', description: 'Critiques retro evaluations', model_id: 'moonshotai/Kimi-K2.5' },
  retro_generator: { agent_name: 'Retro Generator', description: 'Generates retro commentary', model_id: 'moonshotai/Kimi-K2.5' },
  retro_commentary: { agent_name: 'Retro Commentary', description: 'Daily retro narrative', model_id: 'moonshotai/Kimi-K2.5' },
  news_examiner: { agent_name: 'News Examiner', description: 'Classifies incoming news', model_id: 'minimax/minimax-m2.7' },
  catalysts: { agent_name: 'Catalyst Discovery', description: 'Discovers catalysts from news', model_id: 'moonshotai/Kimi-K2.5' },
  capital_events: { agent_name: 'Capital Events', description: 'Detects capital events', model_id: 'minimax/minimax-m2.7' },
  watchlist_sector_evaluator: { agent_name: 'Watchlist Evaluator', description: 'Evaluates watchlist sectors', model_id: 'moonshotai/Kimi-K2.5' },
  watchlist_coordinator: { agent_name: 'Watchlist Coordinator', description: 'Coordinates watchlist updates', model_id: 'moonshotai/Kimi-K2.5' },
  midday: { agent_name: 'Midday Check', description: 'Intraday position check', model_id: 'moonshotai/Kimi-K2.5' },
  sector_rotation: { agent_name: 'Sector Rotation', description: 'Sector momentum analysis', model_id: 'moonshotai/Kimi-K2.5' },
  positions: { agent_name: 'Position Monitor', description: 'Single-agent position monitor (inactive)', model_id: 'moonshotai/Kimi-K2.5' },
  alert_analyst: { agent_name: 'Alert Analyst', description: 'Analyzes triggered alerts', model_id: 'moonshotai/Kimi-K2.5' },
}

const EDGES = [
  { source: 'market_level', target: 'sector', label: 'regime' },
  { source: 'market_level', target: 'longterm' },
  { source: 'market_level', target: 'positions_technical' },

  { source: 'positions_technical', target: 'positions_aggregator' },
  { source: 'positions_value', target: 'positions_aggregator' },
  { source: 'positions_thesis', target: 'positions_aggregator' },
  { source: 'positions_pev_alert', target: 'positions_pev_verifier' },
  { source: 'positions_pev_verifier', target: 'positions_aggregator' },

  { source: 'positions_aggregator', target: 'trading_mode', label: 'alerts' },

  { source: 'trading_mode', target: 'position_strategist' },
  { source: 'trading_mode', target: 'entry_strategist' },

  { source: 'position_strategist', target: 'synthesis', label: 'position guidance' },
  { source: 'entry_strategist', target: 'synthesis', label: 'entry strategy' },
  { source: 'sector', target: 'synthesis', label: 'signals' },
  { source: 'longterm', target: 'synthesis' },
  { source: 'market_level', target: 'synthesis' },

  { source: 'synthesis', target: 'critic' },
  { source: 'critic', target: 'refiner' },


  { source: 'retro_evaluator', target: 'retro_generator', label: 'evaluations' },

  { source: 'news_examiner', target: 'catalysts', label: 'classified' },
  { source: 'news_examiner', target: 'capital_events', label: 'classified' },

  { source: 'watchlist_sector_evaluator', target: 'watchlist_coordinator', label: 'evaluations' },
]

const PIPELINES = [
  {
    id: 'morning',
    name: 'Morning Brief',
    phases: [
      { label: 'Phase 1: Market Context', agents: ['market_level'] },
      {
        label: 'Phase 2: Analysis',
        agents: [
          'sector',
          'longterm',
          'positions_technical',
          'positions_value',
          'positions_thesis',
          'positions_aggregator',
          'positions_pev_alert',
          'positions_pev_verifier',
        ],
      },
      { label: 'Phase 3: Mode', agents: ['trading_mode'] },
      { label: 'Phase 3d: Strategy', agents: ['position_strategist', 'entry_strategist'] },
      { label: 'Phase 4: Output', agents: ['synthesis', 'critic', 'refiner'] },
    ],
    agents: [
      'market_level',
      'sector',
      'longterm',
      'positions_technical',
      'positions_value',
      'positions_thesis',
      'positions_aggregator',
      'positions_pev_alert',
      'positions_pev_verifier',
      'trading_mode',
      'position_strategist',
      'entry_strategist',
      'synthesis',
      'critic',
      'refiner',
    ],
  },
  {
    id: 'retro',
    name: 'Retrospective',
    agents: ['retro_evaluator', 'retro_generator'],
  },
  {
    id: 'news',
    name: 'News Pipeline',
    phases: [
      { label: 'Classify', agents: ['news_examiner'] },
      { label: 'Discover', agents: ['catalysts', 'capital_events'] },
    ],
    agents: ['news_examiner', 'catalysts', 'capital_events'],
  },
  {
    id: 'watchlist',
    name: 'Watchlist',
    agents: ['watchlist_sector_evaluator', 'watchlist_coordinator'],
  },
  {
    id: 'standalone',
    name: 'Standalone',
    agents: ['midday', 'sector_rotation', 'positions', 'alert_analyst'],
  },
]

/** Returns fully static graph data — no DB query needed. */
export function getAgentGraphData(): AgentGraphData {
  const agents: StaticAgent[] = Object.entries(AGENTS).map(([key, data]) => ({
    agent_key: key,
    ...data,
  }))
  return { agents, edges: EDGES, pipelines: PIPELINES }
}
