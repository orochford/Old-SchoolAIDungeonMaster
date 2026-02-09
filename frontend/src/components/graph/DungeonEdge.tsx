import { memo, useState } from 'react'
import {
  BaseEdge,
  getBezierPath,
  EdgeLabelRenderer,
  type EdgeProps,
} from '@xyflow/react'

function DungeonEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
}: EdgeProps) {
  const [hovered, setHovered] = useState(false)
  const isSecret = (data as Record<string, unknown>)?.isSecret as boolean
  const isOneWay = (data as Record<string, unknown>)?.isOneWay as boolean
  const direction = (data as Record<string, unknown>)?.direction as string

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  })

  return (
    <>
      {/* Invisible wider path for hover detection */}
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={20}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      />
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: isSecret ? '#8855cc' : '#6a6250',
          strokeWidth: hovered ? 2.5 : 1.5,
          strokeDasharray: isSecret ? '6 4' : undefined,
          opacity: hovered ? 1 : 0.6,
          transition: 'all 0.2s',
        }}
        markerEnd={isOneWay ? markerEnd : undefined}
      />
      {hovered && direction && (
        <EdgeLabelRenderer>
          <div
            className="absolute font-['IBM_Plex_Mono',monospace] text-[10px] px-1.5 py-0.5 rounded pointer-events-none"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              background: isSecret ? 'rgba(136,85,204,0.2)' : 'rgba(26,24,22,0.9)',
              color: isSecret ? '#bb99ee' : '#b8a060',
              border: `1px solid ${isSecret ? 'rgba(136,85,204,0.4)' : 'rgba(180,160,100,0.3)'}`,
            }}
          >
            {direction.toUpperCase()}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}

export const DungeonEdge = memo(DungeonEdgeComponent)
