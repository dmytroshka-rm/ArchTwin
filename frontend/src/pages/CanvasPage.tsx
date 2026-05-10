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
import { useLLMSettingsStore } from '@/store/llmSettingsStore'
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
  const { firestoreReady } = useFirestoreSync()  // Auto-load from Firestore + auto-save on changes

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
    // Wait for both backend handshake AND Firestore load before deciding
    if (backendCompatible === null || !firestoreReady) return

    if (!ready && !baselineRef) {
      // No saved data in Firestore — load demo
      loadDemo()
    } else if (!ready && baselineRef) {
      // Firestore restored data — just mark ready
      setReady(true)
    }
  }, [backendCompatible, firestoreReady, ready, baselineRef, loadDemo])

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
        <button onClick={() => useLLMSettingsStore.getState().openSettings()} className="text-slate-500 hover:text-slate-300 mr-3 flex items-center gap-1">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
          AI Model
        </button>
        <button onClick={() => navigate('/pricing')} className="text-slate-500 hover:text-slate-300 mr-3">Pricing</button>
        <button onClick={() => navigate('/billing')} className="text-slate-500 hover:text-slate-300 mr-3">Billing</button>
        <button onClick={() => navigate('/instructions')} className="text-slate-500 hover:text-slate-300 mr-3">Instructions</button>
        <button onClick={() => { signOut(); navigate('/') }} className="text-slate-500 hover:text-status-warn">Sign Out</button>
      </div>

      {/* Email verification notice */}
      {user && !user.emailVerified && user.providerData[0]?.providerId === 'password' && (
        <div className="bg-canvas-accent/10 text-canvas-accent text-xs px-4 py-1.5 flex items-center gap-2 shrink-0 border-b border-canvas-accent/20">
          <span>Please verify your email address.</span>
          <button onClick={() => { import('firebase/auth').then(m => m.sendEmailVerification(user)) }} className="underline hover:no-underline">Resend</button>
        </div>
      )}

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
