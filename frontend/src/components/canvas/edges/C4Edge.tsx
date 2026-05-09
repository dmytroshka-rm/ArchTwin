/**
 * C4 edge — visually distinguishes relation types and cross-boundary risks.
 */

import { memo } from 'react'
import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  type EdgeProps,
  type Edge,
} from '@xyflow/react'
import clsx from 'clsx'
import type { RelationType } from '@/generated/isa.types'

// React Flow v12 requires edge data to extend Record<string, unknown>
export type C4EdgeData = {
  relationType?: RelationType
  protocol?: string
  crosses_trust_boundary?: boolean
  crosses_bounded_context?: boolean
  adr_required?: boolean
  data_classification?: string
  criticality?: 'high' | 'medium' | 'low'
  [key: string]: unknown
}

export type C4EdgeType = Edge<C4EdgeData>

const EDGE_STYLE: Record<RelationType, { stroke: string; strokeDasharray?: string }> = {
  synchronous:  { stroke: '#4f6ef7' },
  asynchronous: { stroke: '#f59e0b', strokeDasharray: '6 3' },
  data_access:  { stroke: '#22c55e' },
  streaming:    { stroke: '#a855f7', strokeDasharray: '2 2' },
  batch:        { stroke: '#64748b', strokeDasharray: '8 4' },
  external:     { stroke: '#94a3b8', strokeDasharray: '4 4' },
}

export const C4Edge = memo(function C4Edge({
  id,
  sourceX, sourceY, targetX, targetY,
  sourcePosition, targetPosition,
  data,
  markerEnd,
}: EdgeProps<C4EdgeType>) {
  const relType    = (data?.relationType ?? 'synchronous') as RelationType
  const edgeStyle  = EDGE_STYLE[relType] ?? EDGE_STYLE.synchronous
  const isBoundary = Boolean(data?.crosses_trust_boundary) || Boolean(data?.crosses_bounded_context)
  const isRisky    = Boolean(data?.adr_required) || data?.criticality === 'high'

  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX, sourceY, targetX, targetY,
    sourcePosition, targetPosition,
  })

  const strokeColor = isRisky ? '#ef4444' : isBoundary ? '#f59e0b' : edgeStyle.stroke
  const protocol = data?.protocol as string | undefined

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: strokeColor,
          strokeWidth: 1.5,
          strokeDasharray: edgeStyle.strokeDasharray,
        }}
      />

      {/* Label rendered in DOM for sharp rendering */}
      {(protocol || isBoundary) && (
        <EdgeLabelRenderer>
          <div
            className={clsx(
              'absolute pointer-events-none',
              'bg-canvas-surface border border-canvas-border',
              'rounded px-1.5 py-0.5 text-[10px] font-mono',
              isRisky ? 'text-status-fail border-status-fail/40' :
              isBoundary ? 'text-status-warn border-status-warn/40' :
              'text-slate-400',
            )}
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            }}
          >
            {isBoundary && <span className="mr-1">⚠</span>}
            {protocol}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
})
