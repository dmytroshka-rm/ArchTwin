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
  selected,
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

  const strokeColor = selected
    ? '#4f6ef7'
    : isRisky ? '#ef4444' : isBoundary ? '#f59e0b' : edgeStyle.stroke
  const protocol = data?.protocol as string | undefined

  return (
    <>
      {/* Invisible wider path for easier click targeting */}
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={14}
        className="cursor-pointer"
      />

      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: strokeColor,
          strokeWidth: selected ? 2.5 : 1.5,
          strokeDasharray: edgeStyle.strokeDasharray,
          filter: selected ? 'drop-shadow(0 0 4px rgba(79,110,247,0.5))' : undefined,
          transition: 'stroke-width 0.15s, stroke 0.15s',
        }}
      />

      {/* Label — always show (protocol or relation type) */}
      <EdgeLabelRenderer>
        <div
          className={clsx(
            'absolute',
            'bg-canvas-surface/90 border',
            'rounded px-1.5 py-0.5 text-[10px] font-mono cursor-pointer',
            'hover:border-canvas-accent/50 transition-colors',
            selected ? 'text-canvas-accent border-canvas-accent/40' :
            isRisky ? 'text-status-fail border-status-fail/40' :
            isBoundary ? 'text-status-warn border-status-warn/40' :
            'text-slate-500 border-canvas-border/60',
          )}
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            pointerEvents: 'all',
          }}
        >
          {isBoundary && <span className="mr-1">⚠</span>}
          {protocol || relType.replace('_', ' ')}
        </div>
      </EdgeLabelRenderer>
    </>
  )
})
