import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { formatAuthError } from '@/lib/authErrors'
import { useAuth } from '@/lib/useAuth'
import clsx from 'clsx'

interface Props {
  mode: 'login' | 'register'
}

export function AuthPage({ mode }: Props) {
  const { signIn, signUp, signInWithGoogle, error, resendVerification } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)
  const [verificationSent, setVerificationSent] = useState(false)

  const isRegister = mode === 'register'

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setLocalError(null)

    try {
      if (isRegister) {
        if (!name.trim()) {
          setLocalError('Name is required')
          setLoading(false)
          return
        }
        await signUp(email, password, name)
        setVerificationSent(true)
      } else {
        await signIn(email, password)
      }
      navigate('/canvas')
    } catch (err: unknown) {
      setLocalError(formatAuthError(err))
    } finally {
      setLoading(false)
    }
  }

  const handleGoogle = async () => {
    setLoading(true)
    setLocalError(null)
    try {
      await signInWithGoogle()
      navigate('/canvas')
    } catch (err: unknown) {
      setLocalError(formatAuthError(err))
    } finally {
      setLoading(false)
    }
  }

  const displayError = localError ?? (error ? formatAuthError(new Error(error)) : null)

  return (
    <div className="min-h-screen bg-canvas-bg flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link to="/" className="inline-block">
            <span className="text-canvas-accent font-bold font-mono text-xl">ArchTwin</span>
          </Link>
          <h1 className="text-lg text-slate-200 mt-3 font-semibold">
            {isRegister ? 'Create Account' : 'Sign In'}
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            {isRegister ? 'Start designing your architecture' : 'Welcome back'}
          </p>
        </div>

        {/* Verification sent notice */}
        {verificationSent && (
          <div className="bg-status-pass/10 border border-status-pass/30 rounded-xl p-4 mb-4 text-center">
            <div className="text-status-pass text-sm font-medium mb-1">Verification email sent!</div>
            <p className="text-[11px] text-slate-400 mb-2">Check your inbox and click the link to verify your account.</p>
            <button
              type="button"
              onClick={async () => { await resendVerification(); setLocalError(null) }}
              className="text-[11px] text-canvas-accent hover:underline"
            >
              Resend verification email
            </button>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="bg-canvas-surface border border-canvas-border rounded-xl p-6 flex flex-col gap-4">
          {/* Google */}
          <button
            type="button"
            onClick={handleGoogle}
            disabled={loading}
            className="w-full py-2.5 border border-canvas-border rounded-lg text-sm text-slate-300 hover:border-slate-500 hover:bg-canvas-border/20 transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
            </svg>
            Continue with Google
          </button>

          <div className="flex items-center gap-3">
            <div className="flex-1 border-t border-canvas-border" />
            <span className="text-[10px] text-slate-600 uppercase">or</span>
            <div className="flex-1 border-t border-canvas-border" />
          </div>

          {/* Name (register only) */}
          {isRegister && (
            <div>
              <label className="text-[11px] text-slate-500 mb-1 block">Full Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full bg-canvas-bg border border-canvas-border rounded-lg px-3 py-2 text-sm text-slate-200 outline-none focus:border-canvas-accent"
                placeholder="John Architect"
                required
              />
            </div>
          )}

          {/* Email */}
          <div>
            <label className="text-[11px] text-slate-500 mb-1 block">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-canvas-bg border border-canvas-border rounded-lg px-3 py-2 text-sm text-slate-200 outline-none focus:border-canvas-accent"
              placeholder="you@example.com"
              required
            />
          </div>

          {/* Password */}
          <div>
            <label className="text-[11px] text-slate-500 mb-1 block">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-canvas-bg border border-canvas-border rounded-lg px-3 py-2 text-sm text-slate-200 outline-none focus:border-canvas-accent"
              placeholder={isRegister ? 'Min 6 characters' : 'Your password'}
              minLength={6}
              required
            />
          </div>

          {/* Error */}
          {displayError && (
            <div className="bg-status-fail/10 border border-status-fail/30 rounded-lg px-3 py-2 text-[11px] text-status-fail">
              {displayError}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            className={clsx(
              'w-full py-2.5 rounded-lg text-sm font-semibold transition-colors',
              loading
                ? 'bg-canvas-border/50 text-slate-600 cursor-not-allowed'
                : 'bg-canvas-accent text-white hover:bg-canvas-accent/80',
            )}
          >
            {loading ? 'Please wait...' : isRegister ? 'Create Account' : 'Sign In'}
          </button>
        </form>

        {/* Toggle */}
        <p className="text-center text-xs text-slate-500 mt-4">
          {isRegister ? (
            <>Already have an account? <Link to="/login" className="text-canvas-accent hover:underline">Sign In</Link></>
          ) : (
            <>Don't have an account? <Link to="/register" className="text-canvas-accent hover:underline">Create one</Link></>
          )}
        </p>
      </div>
    </div>
  )
}
