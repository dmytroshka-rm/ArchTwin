/**
 * TeamInviteModal — invite team members by email.
 */

import { useState, useCallback } from 'react'
import { api } from '@/api/client'

interface Props {
  open: boolean
  onClose: () => void
}

export function TeamInviteModal({ open, onClose }: Props) {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<'member' | 'admin' | 'viewer'>('member')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleInvite = useCallback(async () => {
    if (!email.trim()) return
    setLoading(true)
    setError(null)
    setSuccess(false)
    try {
      await api.post('/team/invite', { email: email.trim(), role })
      setSuccess(true)
      setEmail('')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to send invite')
    } finally {
      setLoading(false)
    }
  }, [email, role])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-canvas-surface border border-canvas-border rounded-xl shadow-2xl w-full max-w-md mx-4 p-6">
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-500 hover:text-slate-300">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        <h2 className="text-base font-bold text-slate-100 mb-1">Invite Team Member</h2>
        <p className="text-[11px] text-slate-500 mb-5">They will receive an email with an invite link.</p>

        <div className="space-y-3">
          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Email address</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="colleague@company.com"
              className="w-full bg-canvas-bg border border-canvas-border rounded-lg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-canvas-accent"
              onKeyDown={(e) => { if (e.key === 'Enter') handleInvite() }}
            />
          </div>

          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Role</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as 'member' | 'admin' | 'viewer')}
              className="w-full bg-canvas-bg border border-canvas-border rounded-lg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-canvas-accent appearance-none"
            >
              <option value="viewer">Viewer — can view architecture</option>
              <option value="member">Member — can edit and simulate</option>
              <option value="admin">Admin — full access + billing</option>
            </select>
          </div>

          {error && (
            <div className="text-[11px] text-status-fail bg-status-fail/10 border border-status-fail/20 rounded px-3 py-2">{error}</div>
          )}

          {success && (
            <div className="text-[11px] text-status-pass bg-status-pass/10 border border-status-pass/20 rounded px-3 py-2">
              Invite sent successfully!
            </div>
          )}

          <button
            onClick={handleInvite}
            disabled={loading || !email.trim()}
            className="w-full py-2.5 bg-canvas-accent text-white rounded-lg font-semibold text-sm hover:bg-canvas-accent/80 disabled:opacity-50 transition-colors"
          >
            {loading ? 'Sending...' : 'Send Invite'}
          </button>
        </div>
      </div>
    </div>
  )
}
