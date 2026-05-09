import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: {
          bg: '#0f1117',
          surface: '#1a1d27',
          border: '#2d3148',
          accent: '#4f6ef7',
        },
        tier: {
          1: '#ef4444',
          standard: '#f59e0b',
          auxiliary: '#6b7280',
        },
        status: {
          pass: '#22c55e',
          fail: '#ef4444',
          warn: '#f59e0b',
          info: '#3b82f6',
          blocked: '#dc2626',
          stale: '#78350f',
        },
        fidelity: {
          decision: '#22c55e',
          exploratory: '#f59e0b',
          blocked: '#ef4444',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config
