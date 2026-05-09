/**
 * Firebase configuration for ISA-CAD.
 * All values come from Vite env (frontend/.env) — see .env.example.
 */

import { initializeApp, type FirebaseOptions } from 'firebase/app'
import { getAuth, GoogleAuthProvider } from 'firebase/auth'
import { getFirestore } from 'firebase/firestore'
import { getAnalytics, type Analytics } from 'firebase/analytics'

function readEnv(key: string): string | undefined {
  const v = import.meta.env[key as keyof ImportMetaEnv] as string | undefined
  return typeof v === 'string' && v.trim() !== '' ? v.trim() : undefined
}

function requireEnv(key: string): string {
  const v = readEnv(key)
  if (!v) {
    throw new Error(
      `[Firebase] Missing ${key}. Copy frontend/.env.example to frontend/.env and set your web app config.`,
    )
  }
  return v
}

const messagingSenderId =
  readEnv('VITE_FIREBASE_MESSAGING_SENDER_ID') ?? readEnv('VITE_FIREBASE_MESSAGING_ID')

if (!messagingSenderId) {
  throw new Error(
    '[Firebase] Set VITE_FIREBASE_MESSAGING_SENDER_ID (or legacy VITE_FIREBASE_MESSAGING_ID) in frontend/.env',
  )
}

const firebaseConfig: FirebaseOptions = {
  apiKey: requireEnv('VITE_FIREBASE_API_KEY'),
  authDomain: requireEnv('VITE_FIREBASE_AUTH_DOMAIN'),
  projectId: requireEnv('VITE_FIREBASE_PROJECT_ID'),
  storageBucket: requireEnv('VITE_FIREBASE_STORAGE_BUCKET'),
  messagingSenderId,
  appId: requireEnv('VITE_FIREBASE_APP_ID'),
}

const measurementId = readEnv('VITE_FIREBASE_MEASUREMENT_ID')
if (measurementId) {
  firebaseConfig.measurementId = measurementId
}

const app = initializeApp(firebaseConfig)

export const auth = getAuth(app)
export const db = getFirestore(app)
export const googleProvider = new GoogleAuthProvider()

function initAnalytics(): Analytics | null {
  if (typeof window === 'undefined' || !measurementId) return null
  try {
    return getAnalytics(app)
  } catch {
    return null
  }
}

/** Null when `VITE_FIREBASE_MEASUREMENT_ID` is unset or Analytics is unavailable. */
export const analytics = initAnalytics()
