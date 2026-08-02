import type { Node, Edge } from '@xyflow/react'
import type { AgentGraphData, StaticAgent } from '../types'
import { getModelEdgeColor } from './models'

// Layout constants
const NODE_W = 200
const NODE_H = 72
const COL_GAP = 280
const ROW_GAP = 88
const PIPELINE_GAP_Y = 180
const GROUP_PAD = 24

/** Accent colors per pipeline — industrial control panel aesthetic */
const GROUP_ACCENTS: Record<string, { border: string; bg: string; label: string }> = {
  morning:    { border: 'oklch(0.7 0.15 160 / 25%)',  bg: 'oklch(0.7 0.15 160 / 4%)',  label: 'oklch(0.7 0.12 160)' },
  retro:      { border: 'oklch(0.75 0.15 55 / 25%)',  bg: 'oklch(0.75 0.15 55 / 4%)',  label: 'oklch(0.75 0.12 55)' },
  news:       { border: 'oklch(0.7 0.14 220 / 25%)',  bg: 'oklch(0.7 0.14 220 / 4%)',  label: 'oklch(0.7 0.12 220)' },
  watchlist:  { border: 'oklch(0.75 0.14 45 / 25%)',   bg: 'oklch(0.75 0.14 45 / 4%)',   label: 'oklch(0.75 0.12 45)' },
  standalone: { border: 'oklch(0.4 0 0 / 25%)',       bg: 'oklch(0.4 0 0 / 4%)',        label: 'oklch(0.5 0 0)' },
}

/** Position map: agent_key → [col, row] within its pipeline */
const MORNING_POSITIONS: Record<string, [number, number]> = {
  // Phase 1 — col 0 (centered between analysis + positions)
  market_level: [0, 2],
  // Phase 2a — col 1 top (analysis → synthesis)
  sector: [1, 0],
  longterm: [1, 1],
  // Phase 2b — col 1 bottom (position sub-agents)
  positions_technical: [1, 3],
  positions_value: [1, 4],
  positions_thesis: [1, 5],
  positions_pev_alert: [1, 6],
  // Phase 2c — col 2 (aggregation)
  positions_pev_verifier: [2, 6],
  positions_aggregator: [2, 4],
  // Phase 3 — col 3
  trading_mode: [3, 2],
  // Phase 3d — col 4 (split strategy agents)
  position_strategist: [4, 1],
  entry_strategist: [4, 3],
  // Phase 4 — col 5 (output chain, vertical)
  synthesis: [5, 0],
  critic: [5, 1],
  refiner: [5, 2],
}

const RETRO_POSITIONS: Record<string, [number, number]> = {
  retro_evaluator: [0, 0],
  retro_eval_critic: [1, 0],
  retro_generator: [2, 0],
}

const NEWS_POSITIONS: Record<string, [number, number]> = {
  news_examiner: [0, 0],
  catalysts: [1, 0],
  capital_events: [1, 1],
}

const WATCHLIST_POSITIONS: Record<string, [number, number]> = {
  watchlist_sector_evaluator: [0, 0],
  watchlist_coordinator: [1, 0],
}

const STANDALONE_POSITIONS: Record<string, [number, number]> = {
  midday: [0, 0],
  sector_rotation: [0, 1],
  positions: [0, 2],
  alert_analyst: [0, 3],
}

interface LayoutResult {
  nodes: Node[]
  edges: Edge[]
}

function agentToNode(
  agent: StaticAgent,
  x: number,
  y: number,
  onSelect: (key: string) => void
): Node {
  return {
    id: agent.agent_key,
    type: 'agent',
    position: { x, y },
    data: {
      agent_key: agent.agent_key,
      agent_name: agent.agent_name,
      description: agent.description,
      model_id: agent.model_id,
      onSelect,
    },
    width: NODE_W,
    height: NODE_H,
  }
}

function makeGroupNode(
  id: string,
  pipelineId: string,
  label: string,
  x: number,
  y: number,
  w: number,
  h: number,
  agentCount?: number
): Node {
  const accent = GROUP_ACCENTS[pipelineId] ?? GROUP_ACCENTS.standalone
  return {
    id,
    type: 'pipeline-group',
    position: { x, y },
    data: { label, labelColor: accent.label, agentCount },
    style: {
      width: w,
      height: h,
      border: `1px solid ${accent.border}`,
      borderRadius: '12px',
      backgroundColor: accent.bg,
      padding: 0,
    },
    selectable: false,
    draggable: false,
  }
}

export function computeLayout(
  data: AgentGraphData,
  onSelect: (key: string) => void
): LayoutResult {
  const agentMap = new Map<string, StaticAgent>()
  for (const a of data.agents) agentMap.set(a.agent_key, a)

  const nodes: Node[] = []
  const originX = 60
  const originY = 80

  // --- Morning Brief pipeline ---
  const morningAgentCount = Object.keys(MORNING_POSITIONS).length
  const morningLabel = makeGroupNode(
    'group-morning',
    'morning',
    'Morning Brief Pipeline',
    originX - GROUP_PAD,
    originY - 44,
    6 * COL_GAP + NODE_W + GROUP_PAD * 2,
    7 * ROW_GAP + NODE_H + GROUP_PAD + 44,
    morningAgentCount
  )
  nodes.push(morningLabel)

  for (const [key, [col, row]] of Object.entries(MORNING_POSITIONS)) {
    const agent = agentMap.get(key)
    if (!agent) continue
    const x = originX + col * COL_GAP
    const y = originY + row * ROW_GAP
    nodes.push(agentToNode(agent, x, y, onSelect))
  }

  // --- Retro pipeline ---
  const retroOriginY =
    originY + 7 * ROW_GAP + NODE_H + PIPELINE_GAP_Y

  const retroLabel = makeGroupNode(
    'group-retro',
    'retro',
    'Retrospective Pipeline',
    originX - GROUP_PAD,
    retroOriginY - 44,
    6 * COL_GAP + NODE_W + GROUP_PAD * 2,
    ROW_GAP + NODE_H + GROUP_PAD + 44,
    Object.keys(RETRO_POSITIONS).length
  )
  nodes.push(retroLabel)

  for (const [key, [col, row]] of Object.entries(RETRO_POSITIONS)) {
    const agent = agentMap.get(key)
    if (!agent) continue
    const x = originX + col * COL_GAP
    const y = retroOriginY + row * ROW_GAP
    nodes.push(agentToNode(agent, x, y, onSelect))
  }

  // --- News pipeline ---
  const newsOriginY = retroOriginY + ROW_GAP + NODE_H + PIPELINE_GAP_Y

  const newsLabel = makeGroupNode(
    'group-news',
    'news',
    'News Pipeline',
    originX - GROUP_PAD,
    newsOriginY - 44,
    2 * COL_GAP + NODE_W + GROUP_PAD * 2,
    2 * ROW_GAP + NODE_H + GROUP_PAD + 44,
    Object.keys(NEWS_POSITIONS).length
  )
  nodes.push(newsLabel)

  for (const [key, [col, row]] of Object.entries(NEWS_POSITIONS)) {
    const agent = agentMap.get(key)
    if (!agent) continue
    const x = originX + col * COL_GAP
    const y = newsOriginY + row * ROW_GAP
    nodes.push(agentToNode(agent, x, y, onSelect))
  }

  // --- Watchlist ensemble ---
  const watchlistOriginY = newsOriginY + 2 * ROW_GAP + NODE_H + PIPELINE_GAP_Y

  const watchlistLabel = makeGroupNode(
    'group-watchlist',
    'watchlist',
    'Watchlist Ensemble',
    originX - GROUP_PAD,
    watchlistOriginY - 44,
    2 * COL_GAP + NODE_W + GROUP_PAD * 2,
    ROW_GAP + NODE_H + GROUP_PAD + 44,
    Object.keys(WATCHLIST_POSITIONS).length
  )
  nodes.push(watchlistLabel)

  for (const [key, [col, row]] of Object.entries(WATCHLIST_POSITIONS)) {
    const agent = agentMap.get(key)
    if (!agent) continue
    const x = originX + col * COL_GAP
    const y = watchlistOriginY + row * ROW_GAP
    nodes.push(agentToNode(agent, x, y, onSelect))
  }

  // --- Standalone agents ---
  const standaloneOriginX = originX + 6 * COL_GAP + NODE_W + 120
  const standaloneOriginY = originY

  const standaloneLabel = makeGroupNode(
    'group-standalone',
    'standalone',
    'Standalone',
    standaloneOriginX - GROUP_PAD,
    standaloneOriginY - 44,
    NODE_W + GROUP_PAD * 2,
    4 * ROW_GAP + NODE_H + GROUP_PAD + 44,
    Object.keys(STANDALONE_POSITIONS).length
  )
  nodes.push(standaloneLabel)

  for (const [key, [col, row]] of Object.entries(STANDALONE_POSITIONS)) {
    const agent = agentMap.get(key)
    if (!agent) continue
    const x = standaloneOriginX + col * COL_GAP
    const y = standaloneOriginY + row * ROW_GAP
    nodes.push(agentToNode(agent, x, y, onSelect))
  }

  // --- Edges ---
  const edges: Edge[] = data.edges.map((e, i) => {
    const sourceAgent = agentMap.get(e.source)
    return {
      id: `e-${i}`,
      source: e.source,
      target: e.target,
      type: 'smoothstep',
      animated: true,
      label: e.label,
      labelStyle: {
        fill: 'oklch(0.6 0 0)',
        fontSize: 10,
        fontFamily: 'var(--font-mono)',
      },
      labelBgStyle: {
        fill: 'oklch(0.16 0 0)',
        fillOpacity: 0.9,
      },
      style: {
        stroke: getModelEdgeColor(sourceAgent?.model_id ?? null),
        strokeWidth: 1.5,
      },
    }
  })

  return { nodes, edges }
}
