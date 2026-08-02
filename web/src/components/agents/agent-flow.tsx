import { useMemo, useCallback, useEffect } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  type Node,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { AgentNode } from './agent-node'
import { PipelineGroupNode } from './pipeline-group-node'
import { computeLayout } from '../../lib/agent-graph'
import type { AgentGraphData } from '../../types/index'

const nodeTypes = { agent: AgentNode, 'pipeline-group': PipelineGroupNode }

interface AgentFlowProps {
  data: AgentGraphData
  onSelectAgent: (key: string) => void
}

export function AgentFlow({ data, onSelectAgent }: AgentFlowProps) {
  const { nodes: layoutNodes, edges: layoutEdges } = useMemo(
    () => computeLayout(data, onSelectAgent),
    [data, onSelectAgent]
  )

  const [nodes, setNodes, onNodesChange] = useNodesState(layoutNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(layoutEdges)

  // Sync when upstream data changes (e.g., model_id update)
  useEffect(() => {
    setNodes(layoutNodes)
    setEdges(layoutEdges)
  }, [layoutNodes, layoutEdges, setNodes, setEdges])

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      if (node.type === 'agent') {
        onSelectAgent(node.id)
      }
    },
    [onSelectAgent]
  )

  return (
    <div className="h-full w-full agent-flow-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.12 }}
        minZoom={0.2}
        maxZoom={2}
        nodesDraggable={false}
        nodesConnectable={false}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={24}
          size={1}
          color="oklch(0.28 0 0)"
        />
        <Controls
          showInteractive={false}
          className="!bg-card/95 !border-border/40 !shadow-xl !rounded-lg [&>button]:!bg-card [&>button]:!border-border/20 [&>button]:!text-muted-foreground [&>button:hover]:!bg-accent"
        />
      </ReactFlow>
    </div>
  )
}
