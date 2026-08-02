/** Static agent metadata for graph visualization. */
export interface StaticAgent {
  agent_key: string
  agent_name: string
  description: string | null
  model_id: string
}

// Graph visualization types
export interface AgentEdge {
  source: string
  target: string
  label?: string
}

export interface PipelinePhase {
  label: string
  agents: string[]
}

export interface PipelineGroup {
  id: string
  name: string
  phases?: PipelinePhase[]
  agents: string[]
}

export interface AgentGraphData {
  agents: StaticAgent[]
  edges: AgentEdge[]
  pipelines: PipelineGroup[]
}
