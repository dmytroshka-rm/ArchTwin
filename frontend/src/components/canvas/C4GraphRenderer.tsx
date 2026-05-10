/**
 * C4 Graph Renderer — React Flow canvas with C4 custom nodes and edges.
 * Handles drag-and-drop from palette and dispatches CanvasOperations to backend.
 */

import { useCallback, useRef, useEffect, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
  ConnectionMode,
  type Node,
  type Edge,
  type Connection,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { nanoid } from './nanoid'

import { C4NodeBase, type C4NodeData } from './nodes/C4NodeBase'
import { C4Edge, type C4EdgeData } from './edges/C4Edge'
import { useCanvasStore } from '@/store/canvasStore'
import { useSandboxStore } from '@/store/sandboxStore'
import type { ComponentType, ArchComponent } from '@/generated/isa.types'
import type { CanvasOperationType, CanvasOperationStatus } from '@/generated/canvas-operation.types'

// ── Node / edge type registrations ────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const NODE_TYPES: Record<string, any> = { c4: C4NodeBase }
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const EDGE_TYPES: Record<string, any> = { c4: C4Edge }

// ── Props ─────────────────────────────────────────────────────────────────

import type { ViewMode } from './CanvasShell'
import { canvasApi, type NodeAnnotation } from '@/api/endpoints'

interface Props {
  layerId: string
  editingBlocked: boolean
  viewMode?: ViewMode
}

// ── Component ─────────────────────────────────────────────────────────────

export function C4GraphRenderer({ layerId, editingBlocked, viewMode = 'topology' }: Props) {
  const { addPendingOp, resolvePendingOp, setSelection, nodeLayouts } = useCanvasStore()
  const { upsertComponent, getLayer } = useSandboxStore()

  const layer = getLayer(layerId)
  const reactFlowWrapper = useRef<HTMLDivElement>(null)

  // Compute annotations locally from store data (works for AI-generated components too)
  const [annotations, setAnnotations] = useState<Record<string, NodeAnnotation>>({})
  useEffect(() => {
    if (viewMode === 'topology') { setAnnotations({}); return }
    const components = layer?.components ?? []
    const relations = layer?.relations ?? []
    const result: Record<string, NodeAnnotation> = {}

    for (const comp of components) {
      const compType = comp.type || 'service'
      const tier = comp.tier || 'standard'
      const metrics = comp.observed_metrics || {}

      // Cost
      const costFromMetrics = (metrics as any).monthly_cost_usd
      const costEstimates: Record<string, number> = {
        gateway: 150, service: 200, data_store: 420, cache: 90, queue: 30, external_system: 0,
      }
      const monthlyCost = costFromMetrics ? Number(costFromMetrics) : (costEstimates[compType] ?? 100)
      const costLevel = monthlyCost > 300 ? 'high' : monthlyCost > 100 ? 'medium' : 'low'

      // Security
      const isExternalFacing = compType === 'gateway'
      const hasPii = comp.data_classification === 'restricted' || comp.data_classification === 'confidential'
      const crossesBoundary = relations.some(
        (r) => (r.source_id === comp.id || r.target_id === comp.id) && (r as any).crosses_trust_boundary
      )
      const securityRisk = (isExternalFacing || crossesBoundary) ? 'high' : hasPii ? 'medium' : 'low'

      // Performance
      const latency = metrics.p99_latency_ms
      const rps = metrics.requests_per_second
      const perfRisk = latency && latency > 100 ? 'high' : latency && latency > 50 ? 'medium' : 'low'

      // Blast radius
      const downstreamCount = relations.filter((r) => r.source_id === comp.id).length
      const tierMultiplier = tier === 'tier_1' ? 2.0 : tier === 'standard' ? 1.0 : 0.5
      const blastWeight = downstreamCount * tierMultiplier

      result[comp.id] = {
        cost: { monthly_usd: monthlyCost, label: `$${monthlyCost}/mo`, level: costLevel as any },
        security: { risk: securityRisk as any, external_facing: isExternalFacing, has_pii: hasPii, crosses_boundary: crossesBoundary },
        performance: { risk: perfRisk as any, p99_ms: latency ?? null, rps: rps ?? null },
        blast_radius: { downstream_count: downstreamCount, weight: blastWeight, tier },
      }
    }
    setAnnotations(result)
  }, [viewMode, layer?.components, layer?.relations])

  // Hydrate React Flow state from store (with positions from layout store)
  const initialNodes: Node<C4NodeData>[] = (layer?.components ?? []).map((c) => {
    const layout = nodeLayouts[c.id]
    return {
      id:       c.id,
      type:     'c4',
      position: layout ? { x: layout.x, y: layout.y } : { x: Math.random() * 600, y: Math.random() * 400 },
      data:     { ...c, label: c.name } as C4NodeData,
    }
  })

  const initialEdges: Edge<C4EdgeData>[] = (layer?.relations ?? []).map((r) => ({
    id:     r.id,
    source: r.source_id,
    target: r.target_id,
    type:   'c4',
    data:   { relationType: r.type, protocol: r.protocol, crosses_trust_boundary: (r as any).crosses_trust_boundary } as C4EdgeData,
  }))

  const [nodes, setNodes, onNodesChange] = useNodesState<Node<C4NodeData>>(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge<C4EdgeData>>(initialEdges)

  // Sync React Flow state when store data changes (add/remove/switch layer)
  const storeComponents = layer?.components
  const storeRelations = layer?.relations
  useEffect(() => {
    if (!storeComponents) { setNodes([]); return }
    const storeMap = new Map(storeComponents.map((c) => [c.id, c]))
    setNodes((prev) => {
      // Update existing nodes with fresh data (preserves positions from drag)
      const updated = prev
        .filter((n) => storeMap.has(n.id))
        .map((n) => {
          const c = storeMap.get(n.id)!
          return { ...n, data: { ...c, label: c.name, ...( n.data._viewMode ? { _viewMode: n.data._viewMode, _annotation: n.data._annotation } : {}) } as C4NodeData }
        })
      const updatedIds = new Set(updated.map((n) => n.id))
      // Add new nodes that aren't in React Flow yet
      const added = storeComponents
        .filter((c) => !updatedIds.has(c.id))
        .map((c) => {
          const layout = nodeLayouts[c.id]
          return {
            id: c.id,
            type: 'c4' as const,
            position: layout ? { x: layout.x, y: layout.y } : { x: Math.random() * 600, y: Math.random() * 400 },
            data: { ...c, label: c.name } as C4NodeData,
          }
        })
      return [...updated, ...added]
    })
  }, [storeComponents, setNodes, nodeLayouts])

  useEffect(() => {
    if (!storeRelations) { setEdges([]); return }
    const storeMap = new Map(storeRelations.map((r) => [r.id, r]))
    setEdges((prev) => {
      // Update existing edges with fresh data, remove deleted, add new
      const updated = prev
        .filter((e) => storeMap.has(e.id))
        .map((e) => {
          const r = storeMap.get(e.id)!
          return {
            ...e,
            source: r.source_id,
            target: r.target_id,
            data: { relationType: r.type, protocol: r.protocol, crosses_trust_boundary: (r as any).crosses_trust_boundary } as C4EdgeData,
          }
        })
      const updatedIds = new Set(updated.map((e) => e.id))
      const added = storeRelations
        .filter((r) => !updatedIds.has(r.id))
        .map((r) => ({
          id: r.id,
          source: r.source_id,
          target: r.target_id,
          type: 'c4' as const,
          data: { relationType: r.type, protocol: r.protocol, crosses_trust_boundary: (r as any).crosses_trust_boundary } as C4EdgeData,
        }))
      return [...updated, ...added]
    })
  }, [storeRelations, setEdges])

  // ── Apply view mode annotations to node data ────────────────────────────
  useEffect(() => {
    if (!Object.keys(annotations).length) return
    setNodes((prev) => prev.map((n) => {
      const ann = annotations[n.id]
      if (!ann) return n
      return {
        ...n,
        data: {
          ...n.data,
          _viewMode: viewMode,
          _annotation: ann,
        },
      }
    }))
  }, [annotations, viewMode, setNodes])

  // ── Drag-and-drop from palette (Section 5.1) ────────────────────────────

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
  }, [])

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      if (editingBlocked) return

      const componentType = e.dataTransfer.getData('application/isa-cad-node-type') as ComponentType
      if (!componentType) return

      const bounds = reactFlowWrapper.current?.getBoundingClientRect()
      if (!bounds) return

      const position = {
        x: e.clientX - bounds.left,
        y: e.clientY - bounds.top,
      }

      const opId  = nanoid()
      const tempId = `draft-${nanoid()}`

      // Optimistic node
      const draftNode: Node<C4NodeData> = {
        id:       tempId,
        type:     'c4',
        position,
        data: {
          id:                 tempId,
          name:               `New ${componentType}`,
          type:               componentType,
          label:              `New ${componentType}`,
          validationStatus:   'pending_validation',
          editingBlocked:     false,
        } as C4NodeData,
      }
      setNodes((ns) => [...ns, draftNode])

      // Create pending op
      const op = {
        id:         opId,
        type:       'add_component' as CanvasOperationType,
        status:     'pending_validation' as CanvasOperationStatus,
        created_at: new Date().toISOString(),
        payload:    {
          component: { name: `New ${componentType}`, type: componentType },
          layer_id:  layerId,
          position,
        },
      }
      addPendingOp(op)

      // Backend validation
      canvasApi.validateOperation({
        type:    'add_component',
        payload: op.payload,
      }).then((result) => {
        const finalStatus = result.status
        resolvePendingOp(opId, finalStatus, result.warnings.join('; '))

        if (finalStatus === 'valid' && result.normalized) {
          const confirmed = result.normalized as ArchComponent
          setNodes((ns) =>
            ns.map((n) =>
              n.id === tempId
                ? { ...n, id: confirmed.id ?? tempId, data: { ...confirmed, label: confirmed.name, validationStatus: 'valid' } as C4NodeData }
                : n,
            ),
          )
          upsertComponent(layerId, confirmed)
        } else if (finalStatus === 'invalid' || finalStatus === 'blocked') {
          setNodes((ns) =>
            ns.map((n) =>
              n.id === tempId
                ? { ...n, data: { ...n.data, validationStatus: finalStatus } as C4NodeData }
                : n,
            ),
          )
        }
      }).catch(() => {
        resolvePendingOp(opId, 'invalid', 'Backend validation failed')
        setNodes((ns) => ns.filter((n) => n.id !== tempId))
      })
    },
    [editingBlocked, layerId, addPendingOp, resolvePendingOp, setNodes, upsertComponent],
  )

  // ── Edge connection ──────────────────────────────────────────────────────

  const onConnect = useCallback(
    (connection: Connection) => {
      if (editingBlocked) return
      if (!connection.source || !connection.target) return

      // Create a proper relation and save to store
      const relationId = `rel-${connection.source}-${connection.target}-${Date.now()}`
      const newRelation: import('@/generated/isa.types').ArchRelation = {
        id: relationId,
        source_id: connection.source,
        target_id: connection.target,
        type: 'synchronous',
        protocol: 'HTTPS',
      }

      // Save to sandbox store (persisted via Firestore/localStorage)
      const { upsertRelation } = useSandboxStore.getState()
      upsertRelation(layerId, newRelation)

      // Also add to React Flow local state for immediate visual
      setEdges((es) => addEdge({
        ...connection,
        id: relationId,
        type: 'c4',
        data: { relationType: 'synchronous', protocol: 'HTTPS' } as C4EdgeData,
      }, es))
    },
    [editingBlocked, layerId, setEdges],
  )

  // ── Delete selected nodes/edges (Delete or Backspace) ────────────────────

  // ── Delete with confirmation ──────────────────────────────────────────────
  const [deleteConfirm, setDeleteConfirm] = useState<{ nodes: Node[] } | null>(null)

  const onNodesDelete = useCallback(
    (deleted: Node[]) => {
      if (editingBlocked) return
      setDeleteConfirm({ nodes: deleted })
    },
    [editingBlocked],
  )

  const confirmDelete = useCallback(() => {
    if (!deleteConfirm) return
    const ids = deleteConfirm.nodes.map((n) => n.id)
    const { removeComponent } = useSandboxStore.getState()
    ids.forEach((id) => removeComponent(layerId, id))
    setEdges((es) => es.filter((e) => !ids.includes(e.source) && !ids.includes(e.target)))
    setDeleteConfirm(null)
  }, [deleteConfirm, layerId, setEdges])

  const cancelDelete = useCallback(() => setDeleteConfirm(null), [])

  const onEdgesDelete = useCallback(
    (deleted: Edge[]) => {
      if (editingBlocked) return
      const { removeRelation } = useSandboxStore.getState()
      deleted.forEach((e) => removeRelation(layerId, e.id))
    },
    [editingBlocked, layerId],
  )

  // ── Save positions on drag ───────────────────────────────────────────────

  const onNodeDragStop = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      const { setNodeLayout } = useCanvasStore.getState()
      setNodeLayout(node.id, { x: node.position.x, y: node.position.y })
    },
    [],
  )

  // ── Selection ────────────────────────────────────────────────────────────

  const onSelectionChange = useCallback(
    ({ nodes: ns, edges: es }: { nodes: Node[]; edges: Edge[] }) => {
      setSelection(ns.map((n) => n.id), es.map((e) => e.id))
    },
    [setSelection],
  )

  return (
    <div ref={reactFlowWrapper} className="flex-1 h-full" onDragOver={onDragOver} onDrop={onDrop}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodesDelete={onNodesDelete}
        onEdgesDelete={onEdgesDelete}
        onConnect={onConnect}
        onNodeDragStop={onNodeDragStop}
        onSelectionChange={onSelectionChange}
        deleteKeyCode={editingBlocked ? null : ['Backspace', 'Delete']}
        onMoveEnd={(_, viewport) => {
          useCanvasStore.getState().setViewport({ zoom: viewport.zoom, pan_x: viewport.x, pan_y: viewport.y })
        }}
        nodesDraggable={!editingBlocked}
        nodesConnectable={!editingBlocked}
        elementsSelectable={true}
        connectionRadius={25}
        connectionMode={ConnectionMode.Loose}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#2d3148" />
        <Controls />
        <MiniMap
          nodeColor={(n) => {
            const tier = (n.data as C4NodeData)?.tier as string | undefined
            if (tier === 'tier_1')   return '#ef4444'
            if (tier === 'standard') return '#f59e0b'
            return '#4f6ef7'
          }}
          maskColor="rgba(15, 17, 23, 0.8)"
        />
      </ReactFlow>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={!!deleteConfirm}
        title={`Delete ${deleteConfirm?.nodes.length === 1 ? deleteConfirm.nodes[0].data.name : `${deleteConfirm?.nodes.length} components`}?`}
        message={`This will permanently remove the component${(deleteConfirm?.nodes.length ?? 0) > 1 ? 's' : ''} and all connected relations.`}
        onConfirm={confirmDelete}
        onCancel={cancelDelete}
      />
    </div>
  )
}
