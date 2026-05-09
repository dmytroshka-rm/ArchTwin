/**
 * ArchTwin API client
 * All requests go to the backend — the frontend NEVER computes cost, security
 * or compliance logic itself (Convention v0.6 Section 2.2 / 7.1).
 */

/** Same-origin in dev (Vite proxy); set VITE_API_ORIGIN in production (e.g. https://api.example.com). */
const API_ORIGIN = (import.meta.env.VITE_API_ORIGIN as string | undefined)?.replace(/\/$/, '') ?? ''

/** Full URL for paths starting with `/api` (REST + SSE). */
export function resolveApiUrl(apiPath: string): string {
  if (!API_ORIGIN) return apiPath
  return `${API_ORIGIN}${apiPath}`
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(resolveApiUrl(`/api${path}`), {
    method,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (!res.ok) {
    let errorBody: unknown
    try {
      errorBody = await res.json()
    } catch {
      errorBody = await res.text()
    }
    throw new ApiError(res.status, errorBody, `HTTP ${res.status}: ${path}`)
  }

  return res.json() as Promise<T>
}

export const api = {
  get:    <T>(path: string)              => request<T>('GET',    path),
  post:   <T>(path: string, body: unknown) => request<T>('POST',   path, body),
  put:    <T>(path: string, body: unknown) => request<T>('PUT',    path, body),
  patch:  <T>(path: string, body: unknown) => request<T>('PATCH',  path, body),
  delete: <T>(path: string)              => request<T>('DELETE', path),
}
