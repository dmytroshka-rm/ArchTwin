/**
 * GitIntegration — connect repository and show sync status.
 * Displayed in settings or as a section in the billing page.
 */

import { useState, useCallback } from 'react'
import clsx from 'clsx'

interface GitConfig {
  repoUrl: string
  branch: string
  connected: boolean
  lastSync: string | null
}

const STORAGE_KEY = 'archtwin-git-config'

function loadConfig(): GitConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : { repoUrl: '', branch: 'main', connected: false, lastSync: null }
  } catch {
    return { repoUrl: '', branch: 'main', connected: false, lastSync: null }
  }
}

function saveConfig(config: GitConfig) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config))
}

export function GitIntegration() {
  const [config, setConfig] = useState<GitConfig>(loadConfig)
  const [repoInput, setRepoInput] = useState(config.repoUrl)
  const [branchInput, setBranchInput] = useState(config.branch)
  const [connecting, setConnecting] = useState(false)

  const handleConnect = useCallback(async () => {
    if (!repoInput.trim()) return
    setConnecting(true)
    // Simulate connection delay
    await new Promise((r) => setTimeout(r, 1000))
    const newConfig: GitConfig = {
      repoUrl: repoInput.trim(),
      branch: branchInput.trim() || 'main',
      connected: true,
      lastSync: new Date().toISOString(),
    }
    setConfig(newConfig)
    saveConfig(newConfig)
    setConnecting(false)
  }, [repoInput, branchInput])

  const handleDisconnect = useCallback(() => {
    const newConfig: GitConfig = { repoUrl: '', branch: 'main', connected: false, lastSync: null }
    setConfig(newConfig)
    saveConfig(newConfig)
    setRepoInput('')
    setBranchInput('main')
  }, [])

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wide">Git Integration</h3>

      {config.connected ? (
        <div className="bg-canvas-surface/40 border border-canvas-border rounded-xl p-4">
          {/* Connected status */}
          <div className="flex items-center gap-2 mb-3">
            <span className="w-2 h-2 rounded-full bg-status-pass animate-pulse" />
            <span className="text-[12px] text-status-pass font-medium">Connected</span>
          </div>

          <div className="space-y-2 text-[12px]">
            <div className="flex justify-between">
              <span className="text-slate-500">Repository</span>
              <span className="text-slate-300 font-mono text-[11px] truncate max-w-[200px]">{config.repoUrl}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Branch</span>
              <span className="text-slate-300 font-mono">{config.branch}</span>
            </div>
            {config.lastSync && (
              <div className="flex justify-between">
                <span className="text-slate-500">Last sync</span>
                <span className="text-slate-400">{new Date(config.lastSync).toLocaleString()}</span>
              </div>
            )}
          </div>

          <div className="flex gap-2 mt-4">
            <button
              onClick={() => {
                const updated = { ...config, lastSync: new Date().toISOString() }
                setConfig(updated)
                saveConfig(updated)
              }}
              className="flex-1 text-[11px] py-2 border border-canvas-border text-slate-300 rounded-lg hover:border-slate-500 transition-colors"
            >
              Sync Now
            </button>
            <button
              onClick={handleDisconnect}
              className="text-[11px] py-2 px-3 border border-status-fail/30 text-status-fail/80 rounded-lg hover:bg-status-fail/10 transition-colors"
            >
              Disconnect
            </button>
          </div>

          <p className="text-[10px] text-slate-600 mt-3">
            Architecture changes promoted via "Promote to PR" will create a pull request to this repository.
          </p>
        </div>
      ) : (
        <div className="bg-canvas-surface/40 border border-canvas-border rounded-xl p-4">
          <p className="text-[11px] text-slate-500 mb-3">
            Connect a Git repository to enable PR promotion for architecture changes.
          </p>

          <div className="space-y-3">
            <div>
              <label className="text-[10px] text-slate-500 block mb-1">Repository URL</label>
              <input
                type="text"
                value={repoInput}
                onChange={(e) => setRepoInput(e.target.value)}
                placeholder="https://github.com/org/repo"
                className="w-full bg-canvas-bg border border-canvas-border rounded-lg px-3 py-2 text-[12px] text-slate-200 outline-none focus:border-canvas-accent"
              />
            </div>

            <div>
              <label className="text-[10px] text-slate-500 block mb-1">Branch</label>
              <input
                type="text"
                value={branchInput}
                onChange={(e) => setBranchInput(e.target.value)}
                placeholder="main"
                className="w-full bg-canvas-bg border border-canvas-border rounded-lg px-3 py-2 text-[12px] text-slate-200 outline-none focus:border-canvas-accent"
              />
            </div>

            <button
              onClick={handleConnect}
              disabled={connecting || !repoInput.trim()}
              className={clsx(
                'w-full py-2.5 rounded-lg text-[12px] font-medium transition-colors',
                connecting || !repoInput.trim()
                  ? 'bg-canvas-border/50 text-slate-600 cursor-not-allowed'
                  : 'bg-canvas-accent text-white hover:bg-canvas-accent/80',
              )}
            >
              {connecting ? 'Connecting...' : 'Connect Repository'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
