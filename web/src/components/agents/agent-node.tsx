import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Badge } from '../ui/badge'
import { cn } from '../../lib/utils'
import { getModelStyle, getModelShortName } from '../../lib/models'

export interface AgentNodeData {
  agent_key: string
  agent_name: string
  description: string | null
  model_id: string | null
  onSelect: (key: string) => void
  [key: string]: unknown
}

export const AgentNode = memo(function AgentNode({
  data,
}: NodeProps & { data: AgentNodeData }) {
  const d = data as AgentNodeData
  const style = getModelStyle(d.model_id)
  const shortName = getModelShortName(d.model_id)

  return (
    <>
      <Handle
        type="target"
        position={Position.Left}
        className="!bg-muted-foreground/30 !w-2 !h-2 !border-0"
      />
      <div
        className={cn(
          'px-3 py-2.5 rounded-lg border bg-card/90 backdrop-blur-sm cursor-pointer',
          'transition-all duration-150',
          'hover:scale-[1.03] hover:shadow-lg hover:brightness-110',
          style.border,
          `shadow-md ${style.glow}`,
          'min-w-[180px] max-w-[200px]'
        )}
      >
        {/* Header row */}
        <div className="flex items-center justify-between gap-1.5 mb-1">
          <div className="flex items-center gap-1.5 min-w-0">
            <div className={cn('w-1.5 h-1.5 rounded-full shrink-0', style.dot)} />
            <span className="text-[12px] font-semibold truncate leading-tight">
              {d.agent_name}
            </span>
          </div>
          <Badge
            variant="outline"
            className={cn('text-[9px] px-1 py-0 leading-tight shrink-0 font-mono', style.badge)}
          >
            {shortName}
          </Badge>
        </div>

        {/* Meta row */}
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground/60">
          <span className="font-mono">{d.agent_key}</span>
          {d.agent_key === 'sector' && (
            <Badge
              variant="outline"
              className="text-[8px] px-1 py-0 border-emerald-500/30 text-emerald-400"
            >
              x6
            </Badge>
          )}
          {d.agent_key === 'watchlist_sector_evaluator' && (
            <Badge
              variant="outline"
              className="text-[8px] px-1 py-0 border-amber-500/30 text-amber-400"
            >
              x3
            </Badge>
          )}
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!bg-muted-foreground/30 !w-2 !h-2 !border-0"
      />
    </>
  )
})
