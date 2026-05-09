/**
 * Canvas page — protected route. Loads demo/user architecture and renders the full Canvas.
 */

import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/lib/useAuth'
import { useFirestoreSync } from '@/lib/useFirestoreSync'
import { useVersionHandshake } from '@/hooks/useSimulation'
import { useSimulationStore } from '@/store/simulationStore'
import { useSandboxStore } from '@/store/sandboxStore'
import { useCanvasStore } from '@/store/canvasStore'
import { useBillingStore } from '@/store/billingStore'
import { CanvasShell } from '@/components/canvas/CanvasShell'
import { PlanBadge } from '@/pages/BillingPage'
import { billingApi } from '@/api/endpoints'
import { api } from '@/api/client'
import type { DesignProposal, ArchComponent, ArchRelation } from '@/generated/isa.types'

interface DemoSeedResponse {
  layer: DesignProposal
  components: ArchComponent[]
  relations: ArchRelation[]
  positions: Record<string, { x: number; y: number }>
  baseline_ref: string
}

export function CanvasPage() {
  const { user, loading: authLoading, signOut } = useAuth()
  const navigate = useNavigate()

  useVersionHandshake()
  useFirestoreSync()  // Auto-load from Firestore + auto-save on changes

  // Load billing subscription
  const { plan: currentPlan } = useBillingStore()
  useEffect(() => {
    billingApi.getSubscription().then((info) => {
      useBillingStore.getState().setSubscription(info)
    }).catch(() => { /* ignore */ })
  }, [])

  const { backendCompatible, compatibilityWarning } = useSimulationStore()
  const { setBaselineRef, upsertLayer, setLayerComponents, setLayerRelations, baselineRef } = useSandboxStore()
  const { setActiveLayer, setNodeLayout } = useCanvasStore()
  const [ready, setReady] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const editingBlocked = backendCompatible === false

  // Redirect if not authenticated
  useEffect(() => {
    if (!authLoading && !user) {
      navigate('/login')
    }
  }, [user, authLoading, navigate])

  // Load demo data
  const loadDemo = useCallback(async () => {
    try {
      const data = await api.post<DemoSeedResponse>('/demo/seed', {})
      setBaselineRef(data.baseline_ref)
      upsertLayer(data.layer)
      setActiveLayer(data.layer.id)
      setLayerComponents(data.layer.id, data.components)
      setLayerRelations(data.layer.id, data.relations)
      for (const [nodeId, pos] of Object.entries(data.positions)) {
        setNodeLayout(nodeId, { x: pos.x, y: pos.y })
      }
      setReady(true)
    } catch {
      setError('Could not load demo architecture. Backend might be down.')
      setReady(true)
    }
  }, [setBaselineRef, upsertLayer, setActiveLayer, setLayerComponents, setLayerRelations, setNodeLayout])

  useEffect(() => {
    if (backendCompatible !== null && !ready && !baselineRef) {
      loadDemo()
    } else if (backendCompatible !== null && baselineRef) {
      setReady(true)
    }
  }, [backendCompatible, ready, baselineRef, loadDemo])

  // Loading states
  if (authLoading) {
    return <LoadingScreen text="Checking authentication..." />
  }
  if (!user) return null // redirect happening
  if (!ready) {
    return <LoadingScreen text="Loading architecture..." />
  }

  return (
    <div className="h-full flex flex-col">
      {/* User bar */}
      <div className="h-8 shrink-0 bg-canvas-bg border-b border-canvas-border flex items-center px-4 text-[11px]">
        <span className="text-slate-500">Signed in as</span>
        <span className="text-slate-300 ml-1 font-medium">{user.displayName || user.email}</span>
        <span className="ml-2"><PlanBadge plan={currentPlan} size="small" /></span>
        <div className="flex-1" />
        <button onClick={() => navigate('/pricing')} className="text-slate-500 hover:text-slate-300 mr-3">Pricing</button>
        <button onClick={() => navigate('/billing')} className="text-slate-500 hover:text-slate-300 mr-3">Billing</button>
        <button onClick={() => navigate('/instructions')} className="text-slate-500 hover:text-slate-300 mr-3">Instructions</button>
        <button onClick={() => { signOut(); navigate('/') }} className="text-slate-500 hover:text-status-warn">Sign Out</button>
      </div>

      {/* Compatibility warning */}
      {editingBlocked && (
        <div className="bg-status-blocked text-white text-xs px-4 py-1.5 flex items-center gap-2 shrink-0">
          <span className="font-semibold uppercase">Warning</span>
          <span>{compatibilityWarning}</span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-status-warn/20 text-status-warn text-xs px-4 py-1.5 shrink-0 border-b border-status-warn/30">
          {error}
        </div>
      )}

      <CanvasShell editingBlocked={editingBlocked} />
    </div>
  )
}

function LoadingScreen({ text }: { text: string }) {
  return (
    <div className="h-full flex items-center justify-center bg-canvas-bg">
      <div className="text-center">
        <div className="text-4xl mb-4 animate-pulse">⬡</div>
        <p className="text-sm text-slate-400">{text}</p>
      </div>
    </div>
  )
}
