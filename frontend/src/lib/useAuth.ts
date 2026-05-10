/**
 * Auth hook — provides current user state and auth actions.
 */

import { useState, useEffect, useCallback } from 'react'
import {
  onAuthStateChanged,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signInWithPopup,
  signOut as firebaseSignOut,
  updateProfile,
  sendEmailVerification,
  type User,
} from 'firebase/auth'
import { auth, googleProvider } from './firebase'

export interface AuthState {
  user: User | null
  loading: boolean
  error: string | null
}

export function useAuth() {
  const [state, setState] = useState<AuthState>({
    user: null,
    loading: true,
    error: null,
  })

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      setState({ user, loading: false, error: null })
    })
    return unsubscribe
  }, [])

  const signIn = useCallback(async (email: string, password: string) => {
    setState((s) => ({ ...s, error: null, loading: true }))
    try {
      await signInWithEmailAndPassword(auth, email, password)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Sign in failed'
      setState((s) => ({ ...s, error: msg, loading: false }))
      throw e
    }
  }, [])

  const signUp = useCallback(async (email: string, password: string, displayName: string) => {
    setState((s) => ({ ...s, error: null, loading: true }))
    try {
      const cred = await createUserWithEmailAndPassword(auth, email, password)
      await updateProfile(cred.user, { displayName })
      // Send email verification
      await sendEmailVerification(cred.user).catch(() => { /* non-blocking */ })
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Sign up failed'
      setState((s) => ({ ...s, error: msg, loading: false }))
      throw e
    }
  }, [])

  const resendVerification = useCallback(async () => {
    if (auth.currentUser && !auth.currentUser.emailVerified) {
      await sendEmailVerification(auth.currentUser)
    }
  }, [])

  const signInWithGoogle = useCallback(async () => {
    setState((s) => ({ ...s, error: null, loading: true }))
    try {
      await signInWithPopup(auth, googleProvider)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Google sign in failed'
      setState((s) => ({ ...s, error: msg, loading: false }))
      throw e
    }
  }, [])

  const signOut = useCallback(async () => {
    await firebaseSignOut(auth)
  }, [])

  return {
    user: state.user,
    loading: state.loading,
    error: state.error,
    signIn,
    signUp,
    signInWithGoogle,
    signOut,
    resendVerification,
    isEmailVerified: state.user?.emailVerified ?? false,
  }
}
