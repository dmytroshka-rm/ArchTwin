/**
 * LLM Settings store — user's API key and model preference.
 * Key is stored locally (localStorage) and sent with AI requests.
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type LLMProvider = 'openai' | 'anthropic' | 'google' | 'groq' | 'openrouter'

export interface ModelOption {
  id: string
  name: string
  provider: LLMProvider
  contextWindow: string
  description: string
}

export const AVAILABLE_MODELS: ModelOption[] = [
  // Anthropic
  { id: 'claude-sonnet-4-6', name: 'Claude Sonnet 4.6', provider: 'anthropic', contextWindow: '200K', description: 'Fast, balanced performance' },
  { id: 'claude-opus-4-6', name: 'Claude Opus 4.6', provider: 'anthropic', contextWindow: '1M', description: 'Most capable, extended context' },
  { id: 'claude-haiku-4-5-20251001', name: 'Claude Haiku 4.5', provider: 'anthropic', contextWindow: '200K', description: 'Fastest, most affordable' },
  // OpenAI
  { id: 'gpt-4o', name: 'GPT-4o', provider: 'openai', contextWindow: '128K', description: 'Multimodal, fast' },
  { id: 'gpt-4o-mini', name: 'GPT-4o Mini', provider: 'openai', contextWindow: '128K', description: 'Affordable, quick' },
  { id: 'o3', name: 'o3', provider: 'openai', contextWindow: '200K', description: 'Advanced reasoning' },
  // Google
  { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro', provider: 'google', contextWindow: '1M', description: 'Long context, multimodal' },
  { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash', provider: 'google', contextWindow: '1M', description: 'Fast, cost-effective' },
  // Groq
  { id: 'llama-3.3-70b-versatile', name: 'Llama 3.3 70B', provider: 'groq', contextWindow: '128K', description: 'Open-source, fast inference' },
  { id: 'mixtral-8x7b-32768', name: 'Mixtral 8x7B', provider: 'groq', contextWindow: '32K', description: 'Open-source MoE' },
  // OpenRouter
  { id: 'openrouter/auto', name: 'OpenRouter Auto', provider: 'openrouter', contextWindow: 'Varies', description: 'Auto-routes to best model' },
]

export const PROVIDER_LABELS: Record<LLMProvider, string> = {
  anthropic: 'Anthropic',
  openai: 'OpenAI',
  google: 'Google AI',
  groq: 'Groq',
  openrouter: 'OpenRouter',
}

interface LLMSettingsState {
  // API key (stored in localStorage via persist)
  apiKey: string
  provider: LLMProvider
  selectedModel: string

  // UI
  settingsOpen: boolean

  // Actions
  setApiKey: (key: string) => void
  setProvider: (provider: LLMProvider) => void
  setSelectedModel: (modelId: string) => void
  openSettings: () => void
  closeSettings: () => void
  clearKey: () => void
  isConfigured: () => boolean
}

export const useLLMSettingsStore = create<LLMSettingsState>()(
  persist(
    (set, get) => ({
      apiKey: '',
      provider: 'anthropic',
      selectedModel: 'claude-sonnet-4-6',
      settingsOpen: false,

      setApiKey: (key) => set({ apiKey: key }),
      setProvider: (provider) => {
        // Auto-select first model for this provider
        const firstModel = AVAILABLE_MODELS.find((m) => m.provider === provider)
        set({ provider, selectedModel: firstModel?.id ?? '' })
      },
      setSelectedModel: (modelId) => set({ selectedModel: modelId }),
      openSettings: () => set({ settingsOpen: true }),
      closeSettings: () => set({ settingsOpen: false }),
      clearKey: () => set({ apiKey: '' }),
      isConfigured: () => get().apiKey.length > 0,
    }),
    {
      name: 'archtwin-llm-settings',
      partialize: (state) => ({
        apiKey: state.apiKey,
        provider: state.provider,
        selectedModel: state.selectedModel,
      }),
    }
  )
)
