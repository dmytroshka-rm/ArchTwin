/**
 * LLMSettingsModal — allows users to configure their API key and select a model.
 */

import { useState, useCallback } from 'react'
import {
  useLLMSettingsStore,
  AVAILABLE_MODELS,
  PROVIDER_LABELS,
  type LLMProvider,
} from '@/store/llmSettingsStore'
import { api } from '@/api/client'

const PROVIDERS: LLMProvider[] = ['anthropic', 'openai', 'google', 'groq', 'openrouter']

const API_KEY_HINTS: Record<LLMProvider, string> = {
  anthropic: 'sk-ant-api03-...',
  openai: 'sk-proj-...',
  google: 'AIza...',
  groq: 'gsk_...',
  openrouter: 'sk-or-v1-...',
}

const API_KEY_URLS: Record<LLMProvider, string> = {
  anthropic: 'https://console.anthropic.com/settings/keys',
  openai: 'https://platform.openai.com/api-keys',
  google: 'https://aistudio.google.com/apikey',
  groq: 'https://console.groq.com/keys',
  openrouter: 'https://openrouter.ai/keys',
}

export function LLMSettingsModal() {
  const {
    apiKey,
    provider,
    selectedModel,
    settingsOpen,
    setApiKey,
    setProvider,
    setSelectedModel,
    closeSettings,
    clearKey,
  } = useLLMSettingsStore()

  const [keyInput, setKeyInput] = useState(apiKey)
  const [showKey, setShowKey] = useState(false)
  const [validating, setValidating] = useState(false)
  const [validationResult, setValidationResult] = useState<'valid' | 'invalid' | null>(null)

  const modelsForProvider = AVAILABLE_MODELS.filter((m) => m.provider === provider)

  const handleProviderChange = useCallback((p: LLMProvider) => {
    setProvider(p)
    setValidationResult(null)
  }, [setProvider])

  const handleSave = useCallback(() => {
    setApiKey(keyInput)
    setValidationResult(null)
    closeSettings()
  }, [keyInput, setApiKey, closeSettings])

  const handleValidate = useCallback(async () => {
    if (!keyInput) return
    setValidating(true)
    setValidationResult(null)
    try {
      const res = await api.post<{ valid: boolean }>('/llm/validate-key', {
        api_key: keyInput,
        provider,
        model: selectedModel,
      })
      setValidationResult(res.valid ? 'valid' : 'invalid')
    } catch {
      setValidationResult('invalid')
    } finally {
      setValidating(false)
    }
  }, [keyInput, provider, selectedModel])

  const handleClear = useCallback(() => {
    clearKey()
    setKeyInput('')
    setValidationResult(null)
  }, [clearKey])

  if (!settingsOpen) return null

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={closeSettings} />

      <div className="relative bg-canvas-surface border border-canvas-border rounded-xl shadow-2xl w-full max-w-lg mx-4 max-h-[85vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-canvas-surface border-b border-canvas-border px-6 py-4 flex items-center justify-between rounded-t-xl">
          <div>
            <h2 className="text-base font-bold text-slate-100">AI Model Settings</h2>
            <p className="text-[11px] text-slate-500 mt-0.5">Configure your LLM provider and API key</p>
          </div>
          <button onClick={closeSettings} className="text-slate-500 hover:text-slate-300 transition-colors">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div className="px-6 py-5 space-y-6">
          {/* Provider Selection */}
          <section>
            <label className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold block mb-2">
              Provider
            </label>
            <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
              {PROVIDERS.map((p) => (
                <button
                  key={p}
                  onClick={() => handleProviderChange(p)}
                  className={`text-[11px] px-3 py-2 rounded-lg border transition-colors text-center ${
                    provider === p
                      ? 'border-canvas-accent bg-canvas-accent/10 text-canvas-accent font-medium'
                      : 'border-canvas-border text-slate-400 hover:border-slate-500'
                  }`}
                >
                  {PROVIDER_LABELS[p]}
                </button>
              ))}
            </div>
          </section>

          {/* API Key */}
          <section>
            <label className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold block mb-2">
              API Key
            </label>
            <div className="relative">
              <input
                type={showKey ? 'text' : 'password'}
                value={keyInput}
                onChange={(e) => { setKeyInput(e.target.value); setValidationResult(null) }}
                placeholder={API_KEY_HINTS[provider]}
                className="w-full bg-canvas-bg border border-canvas-border rounded-lg px-3 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:border-canvas-accent focus:outline-none font-mono"
              />
              <button
                onClick={() => setShowKey(!showKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 p-1"
                title={showKey ? 'Hide key' : 'Show key'}
              >
                {showKey ? (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94" />
                    <path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                  </svg>
                ) : (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                )}
              </button>
            </div>

            {/* Key actions */}
            <div className="flex items-center gap-2 mt-2">
              <button
                onClick={handleValidate}
                disabled={!keyInput || validating}
                className="text-[11px] px-3 py-1 border border-canvas-border rounded-md text-slate-400 hover:text-slate-200 hover:border-slate-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {validating ? 'Validating...' : 'Test Key'}
              </button>
              {keyInput && (
                <button
                  onClick={handleClear}
                  className="text-[11px] px-3 py-1 text-status-fail/80 hover:text-status-fail transition-colors"
                >
                  Clear Key
                </button>
              )}
              {validationResult === 'valid' && (
                <span className="text-[11px] text-status-pass flex items-center gap-1">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  Valid
                </span>
              )}
              {validationResult === 'invalid' && (
                <span className="text-[11px] text-status-fail flex items-center gap-1">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                  Invalid key
                </span>
              )}
            </div>

            {/* Get key link */}
            <a
              href={API_KEY_URLS[provider]}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[11px] text-canvas-accent/70 hover:text-canvas-accent mt-2 inline-flex items-center gap-1 transition-colors"
            >
              Get {PROVIDER_LABELS[provider]} API key
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" />
                <polyline points="15 3 21 3 21 9" />
                <line x1="10" y1="14" x2="21" y2="3" />
              </svg>
            </a>
          </section>

          {/* Model Selection */}
          <section>
            <label className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold block mb-2">
              Model
            </label>
            <div className="space-y-1.5">
              {modelsForProvider.map((model) => (
                <button
                  key={model.id}
                  onClick={() => setSelectedModel(model.id)}
                  className={`w-full text-left px-3 py-2.5 rounded-lg border transition-colors ${
                    selectedModel === model.id
                      ? 'border-canvas-accent bg-canvas-accent/5'
                      : 'border-canvas-border hover:border-slate-500'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className={`text-sm font-medium ${selectedModel === model.id ? 'text-canvas-accent' : 'text-slate-200'}`}>
                      {model.name}
                    </span>
                    <span className="text-[10px] text-slate-500 font-mono">{model.contextWindow}</span>
                  </div>
                  <p className="text-[11px] text-slate-500 mt-0.5">{model.description}</p>
                </button>
              ))}
            </div>
          </section>

          {/* Security note */}
          <div className="flex items-start gap-2 bg-status-warn/5 border border-status-warn/20 rounded-lg px-3 py-2.5">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-status-warn shrink-0 mt-0.5">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
            <span className="text-[11px] text-slate-400 leading-relaxed">
              Your API key is stored locally in your browser and sent directly to the provider.
              It is never stored on our servers.
            </span>
          </div>
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 bg-canvas-surface border-t border-canvas-border px-6 py-4 flex justify-end gap-3 rounded-b-xl">
          <button
            onClick={closeSettings}
            className="text-[12px] px-4 py-2 border border-canvas-border text-slate-300 rounded-lg hover:border-slate-500 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="text-[12px] px-5 py-2 bg-canvas-accent text-white rounded-lg font-medium hover:bg-canvas-accent/80 transition-colors"
          >
            Save Settings
          </button>
        </div>
      </div>
    </div>
  )
}
