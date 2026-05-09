/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_ORIGIN?: string
  readonly VITE_FIREBASE_API_KEY?: string
  readonly VITE_FIREBASE_AUTH_DOMAIN?: string
  readonly VITE_FIREBASE_PROJECT_ID?: string
  readonly VITE_FIREBASE_STORAGE_BUCKET?: string
  /** Same as Firebase "messagingSenderId" / GCM sender ID in console */
  readonly VITE_FIREBASE_MESSAGING_SENDER_ID?: string
  /** @deprecated use VITE_FIREBASE_MESSAGING_SENDER_ID */
  readonly VITE_FIREBASE_MESSAGING_ID?: string
  readonly VITE_FIREBASE_APP_ID?: string
  /** Optional — Google Analytics (Measurement ID), e.g. G-XXXXXXXX */
  readonly VITE_FIREBASE_MEASUREMENT_ID?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
