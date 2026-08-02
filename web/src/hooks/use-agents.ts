import { useMemo } from 'react'
import { getAgentGraphData } from '../server/fns/agents'
import type { AgentGraphData } from '../types/agents'

export function useAgentGraph(): AgentGraphData {
  return useMemo(() => getAgentGraphData(), [])
}
