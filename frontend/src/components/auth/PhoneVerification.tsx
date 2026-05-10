/**
 * PhoneVerification — Firebase Phone Auth OTP flow.
 * Used as optional 2FA: user enters phone → receives SMS code → verifies.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import {
  RecaptchaVerifier,
  PhoneAuthProvider,
  linkWithCredential,
  type ConfirmationResult,
} from 'firebase/auth'
import { auth } from '@/lib/firebase'

interface Props {
  onSuccess?: () => void
  onCancel?: () => void
}

export function PhoneVerification({ onSuccess, onCancel }: Props) {
  const [step, setStep] = useState<'phone' | 'code'>('phone')
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState(['', '', '', '', '', ''])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmation, setConfirmation] = useState<ConfirmationResult | null>(null)

  const recaptchaRef = useRef<HTMLDivElement>(null)
  const verifierRef = useRef<RecaptchaVerifier | null>(null)
  const codeInputsRef = useRef<(HTMLInputElement | null)[]>([])

  // Initialize recaptcha
  useEffect(() => {
    if (recaptchaRef.current && !verifierRef.current) {
      verifierRef.current = new RecaptchaVerifier(auth, recaptchaRef.current, {
        size: 'invisible',
      })
    }
    return () => {
      verifierRef.current?.clear()
      verifierRef.current = null
    }
  }, [])

  const handleSendCode = useCallback(async () => {
    if (!phone.trim() || !verifierRef.current) return
    setLoading(true)
    setError(null)
    try {
      const provider = new PhoneAuthProvider(auth)
      const verificationId = await provider.verifyPhoneNumber(phone, verifierRef.current)
      setConfirmation({ verificationId } as unknown as ConfirmationResult)
      setStep('code')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to send code')
    } finally {
      setLoading(false)
    }
  }, [phone])

  const handleVerifyCode = useCallback(async () => {
    const otp = code.join('')
    if (otp.length !== 6 || !confirmation) return
    setLoading(true)
    setError(null)
    try {
      const credential = PhoneAuthProvider.credential(
        (confirmation as unknown as { verificationId: string }).verificationId,
        otp,
      )
      // Link phone to existing account
      if (auth.currentUser) {
        await linkWithCredential(auth.currentUser, credential)
      }
      onSuccess?.()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Invalid code')
    } finally {
      setLoading(false)
    }
  }, [code, confirmation, onSuccess])

  const handleCodeInput = useCallback((index: number, value: string) => {
    if (value.length > 1) value = value.slice(-1)
    if (!/^\d*$/.test(value)) return

    const newCode = [...code]
    newCode[index] = value
    setCode(newCode)

    // Auto-focus next input
    if (value && index < 5) {
      codeInputsRef.current[index + 1]?.focus()
    }

    // Auto-submit when all filled
    if (newCode.every((c) => c) && newCode.join('').length === 6) {
      setTimeout(() => handleVerifyCode(), 100)
    }
  }, [code, handleVerifyCode])

  const handleCodeKeyDown = useCallback((index: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !code[index] && index > 0) {
      codeInputsRef.current[index - 1]?.focus()
    }
  }, [code])

  return (
    <div className="bg-canvas-surface border border-canvas-border rounded-xl p-5 max-w-sm w-full">
      <h3 className="text-sm font-bold text-slate-200 mb-1">
        {step === 'phone' ? 'Phone Verification' : 'Enter Code'}
      </h3>
      <p className="text-[11px] text-slate-500 mb-4">
        {step === 'phone'
          ? 'Add your phone number for additional security.'
          : `We sent a 6-digit code to ${phone}`}
      </p>

      {step === 'phone' && (
        <>
          <input
            type="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="+380XXXXXXXXX"
            className="w-full bg-canvas-bg border border-canvas-border rounded-lg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-canvas-accent mb-3"
          />
          <div ref={recaptchaRef} />
        </>
      )}

      {step === 'code' && (
        <div className="flex gap-2 justify-center mb-4">
          {code.map((digit, i) => (
            <input
              key={i}
              ref={(el) => { codeInputsRef.current[i] = el }}
              type="text"
              inputMode="numeric"
              maxLength={1}
              value={digit}
              onChange={(e) => handleCodeInput(i, e.target.value)}
              onKeyDown={(e) => handleCodeKeyDown(i, e)}
              className="w-10 h-12 bg-canvas-bg border border-canvas-border rounded-lg text-center text-lg font-mono text-slate-200 outline-none focus:border-canvas-accent"
            />
          ))}
        </div>
      )}

      {error && (
        <div className="text-[11px] text-status-fail bg-status-fail/10 rounded px-2 py-1.5 mb-3">{error}</div>
      )}

      <div className="flex gap-2">
        {onCancel && (
          <button onClick={onCancel} className="flex-1 text-[12px] py-2 border border-canvas-border text-slate-300 rounded-lg hover:border-slate-500 transition-colors">
            Cancel
          </button>
        )}
        <button
          onClick={step === 'phone' ? handleSendCode : handleVerifyCode}
          disabled={loading || (step === 'phone' ? !phone.trim() : code.join('').length !== 6)}
          className="flex-1 text-[12px] py-2 bg-canvas-accent text-white rounded-lg font-medium hover:bg-canvas-accent/80 transition-colors disabled:opacity-50"
        >
          {loading ? 'Please wait...' : step === 'phone' ? 'Send Code' : 'Verify'}
        </button>
      </div>
    </div>
  )
}
