import { createFileRoute } from '@tanstack/react-router'
import { ReactFlowProvider } from '@xyflow/react'
import { useAgentGraph } from '../hooks/use-agents'
import { AgentFlow } from '../components/agents/agent-flow'

export const Route = createFileRoute('/agents')({
  component: AgentsPage,
  ssr: false,
})

function AgentsPage() {
  const data = useAgentGraph()

  return (
    <div className="h-[calc(100vh-77px)] relative">
      <ReactFlowProvider>
        <AgentFlow data={data} onSelectAgent={() => {}} />
      </ReactFlowProvider>
    </div>
  )
}
