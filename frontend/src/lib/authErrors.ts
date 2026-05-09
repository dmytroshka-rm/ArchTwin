/**
 * Firebase Auth errors often look like: "Firebase: Error (auth/email-already-in-use)."
 * Stripping the (auth/...) part alone leaves useless text like "Error ."
 */

const AUTH_CODE_MESSAGES: Record<string, string> = {
  'email-already-in-use': 'This email is already registered. Try signing in.',
  'invalid-email': 'Enter a valid email address.',
  'weak-password': 'Use a stronger password (at least 6 characters).',
  'network-request-failed': 'Network error. Check your connection and try again.',
  'too-many-requests': 'Too many attempts. Try again later.',
  'operation-not-allowed':
    'Email/password sign-in is disabled. Enable it in Firebase Console → Authentication → Sign-in method.',
  'invalid-credential': 'Wrong email or password.',
  'user-disabled': 'This account has been disabled.',
  'user-not-found': 'No account found with this email.',
  'wrong-password': 'Wrong password.',
  'popup-closed-by-user': 'Sign-in was cancelled.',
  'cancelled-popup-request': 'Only one sign-in popup at a time.',
  'internal-error': 'Something went wrong. Try again.',
  'unauthorized-domain':
    'This domain is not allowed for Firebase Auth. Add it in Firebase Console → Authentication → Settings → Authorized domains.',
}

export function formatAuthError(err: unknown): string {
  const raw = err instanceof Error ? err.message : typeof err === 'string' ? err : ''
  const codeMatch = raw.match(/auth\/([^)\s]+)/)
  const code = codeMatch?.[1]
  if (code) {
    if (AUTH_CODE_MESSAGES[code]) return AUTH_CODE_MESSAGES[code]
    return code.replace(/-/g, ' ')
  }

  const cleaned = raw
    .replace(/^Firebase:\s*/i, '')
    .replace(/\s*\(auth\/[^)]+\)\.?\s*/g, '')
    .replace(/^Error\.?\s*$/i, '')
    .trim()

  if (cleaned) return cleaned
  return 'Authentication failed. Please try again.'
}
