/**
 * Firebase configuration for ISA-CAD.
 */

import { initializeApp } from 'firebase/app'
import { getAuth, GoogleAuthProvider } from 'firebase/auth'
import { getFirestore } from 'firebase/firestore'
import { getAnalytics } from 'firebase/analytics'

const firebaseConfig = {
  apiKey: "AIzaSyAeAbcgJlcchsVWKHd3PJWvxV7jn11UKE8",
  authDomain: "isa-cad-bd33c.firebaseapp.com",
  projectId: "isa-cad-bd33c",
  storageBucket: "isa-cad-bd33c.firebasestorage.app",
  messagingSenderId: "1088549574077",
  appId: "1:1088549574077:web:27ec94a9f49900d07aaed4",
  measurementId: "G-5E7MZEN293",
}

const app = initializeApp(firebaseConfig)

export const auth = getAuth(app)
export const db = getFirestore(app)
export const analytics = getAnalytics(app)
export const googleProvider = new GoogleAuthProvider()
