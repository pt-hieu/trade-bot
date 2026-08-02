import { memo } from 'react'
import type { NodeProps } from '@xyflow/react'

interface PipelineGroupData {
  label: string
  labelColor?: string
  agentCount?: number
  [key: string]: unknown
}

export const PipelineGroupNode = memo(function PipelineGroupNode({
  data,
  style,
}: NodeProps & { data: PipelineGroupData; style?: React.CSSProperties }) {
  const labelColor = data.labelColor ?? 'oklch(0.5 0 0)'
  const borderColor = (style?.border as string | undefined)
    ?.replace('1px solid ', '') ?? 'oklch(0.4 0 0 / 25%)'

  return (
    <div className="w-full h-full relative">
      {/* Left accent bar */}
      <div
        className="absolute left-0 top-3 bottom-3 w-[3px] rounded-full"
        style={{ backgroundColor: borderColor }}
      />
      {/* Label row */}
      <div className="absolute top-3 left-5 flex items-center gap-2">
        <span
          className="text-xs font-semibold tracking-wide"
          style={{ color: labelColor }}
        >
          {data.label}
        </span>
        {data.agentCount != null && (
          <span
            className="text-[10px] font-mono px-1.5 py-0.5 rounded"
            style={{
              color: labelColor,
              backgroundColor: borderColor,
            }}
          >
            {data.agentCount}
          </span>
        )}
      </div>
    </div>
  )
})
