/**
 * C4 Graph Renderer — React Flow canvas with C4 custom nodes and edges.
 * Handles drag-and-drop from palette and dispatches CanvasOperations to backend.
 */

import { useCallback, useRef, useEffect } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
  type Node,
  type Edge,
  type Connection,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { nanoid } from './nanoid'

import { C4NodeBase, type C4NodeData } from './nodes/C4NodeBase'
import { C4Edge, type C4EdgeData } from './edges/C4Edge'
import { useCanvasStore } from '@/store/canvasStore'
import { useSandboxStore } from '@/store/sandboxStore'
import { canvasApi } from '@/api/endpoints'
import type { ComponentType, ArchComponent } from '@/generated/isa.types'
import type { CanvasOperationType, CanvasOperationStatus } from '@/generated/canvas-operation.types'

// ── Node / edge type registrations ────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const NODE_TYPES: Record<string, any> = { c4: C4NodeBase }
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const EDGE_TYPES: Record<string, any> = { c4: C4Edge }

// ── Props ─────────────────────────────────────────────────────────────────

interface Props {
  layerId: string
  editingBlocked: boolean
}

// ── Component ─────────────────────────────────────────────────────────────

export function C4GraphRenderer({ layerId, editingBlocked }: Props) {
  const { addPendingOp, resolvePendingOp, setSelection, nodeLayouts } = useCanvasStore()
  const { upsertComponent, getLayer } = useSandboxStore()

  const layer = getLayer(layerId)
  const reactFlowWrapper = useRef<HTMLDivElement>(null)

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

  // Sync React Flow state when store data changes (e.g. delete from Inspector)
  const storeComponents = layer?.components
  const storeRelations = layer?.relations
  useEffect(() => {
    if (!storeComponents) return
    const storeIds = new Set(storeComponents.map((c) => c.id))
    setNodes((ns) => ns.filter((n) => storeIds.has(n.id)))
  }, [storeComponents, setNodes])

  useEffect(() => {
    if (!storeRelations) return
    const storeIds = new Set(storeRelations.map((r) => r.id))
    setEdges((es) => es.filter((e) => storeIds.has(e.id)))
  }, [storeRelations, setEdges])

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
      setEdges((es) => addEdge({ ...connection, type: 'c4', data: { relationType: 'synchronous' } as C4EdgeData }, es))
    },
    [editingBlocked, setEdges],
  )

  // ── Delete selected nodes/edges (Delete or Backspace) ────────────────────

  const onNodesDelete = useCallback(
    (deleted: Node[]) => {
      if (editingBlocked) return
      const ids = deleted.map((n) => n.id)
      // Remove from sandbox store
      const { removeComponent } = useSandboxStore.getState()
      ids.forEach((id) => removeComponent(layerId, id))
      // Also remove edges connected to deleted nodes
      setEdges((es) => es.filter((e) => !ids.includes(e.source) && !ids.includes(e.target)))
    },
    [editingBlocked, layerId, setEdges],
  )

  const onEdgesDelete = useCallback(
    (deleted: Edge[]) => {
      if (editingBlocked) return
      const { removeRelation } = useSandboxStore.getState()
      deleted.forEach((e) => removeRelation(layerId, e.id))
    },
    [editingBlocked, layerId],
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
        onSelectionChange={onSelectionChange}
        deleteKeyCode={editingBlocked ? null : ['Backspace', 'Delete']}
        onMoveEnd={(_, viewport) => {
          useCanvasStore.getState().setViewport({ zoom: viewport.zoom, pan_x: viewport.x, pan_y: viewport.y })
        }}
        nodesDraggable={!editingBlocked}
        nodesConnectable={!editingBlocked}
        elementsSelectable={true}
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
    </div>
  )
}
