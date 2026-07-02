const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export function apiUrl(path: string): string {
  return `${BASE_URL}${path}`
}

export class ApiError extends Error {
  status: number
  body?: any
  constructor(response: Response, body?: any) {
    super(body?.message || body?.detail || `API error: ${response.status}`)
    this.status = response.status
    this.body = body
  }
}

export function getApiErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    return err.body?.detail || err.body?.message || err.message
  }
  if (err instanceof Error) return err.message
  return String(err)
}

// Endpoints that must never trigger the global 401 redirect: the login route
// itself and the session probe used to check whether the user is signed in.
// Redirecting on their own 401s would either loop back to the login page or
// fight with the login form's own error handling.
const AUTH_ENDPOINTS = ['/managed/auth/login', '/managed/auth/me']
const LOGIN_PATH = '/managed/login'

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    credentials: 'include',
    ...options,
  })
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    if (
      response.status === 401
      && !AUTH_ENDPOINTS.includes(path)
      && typeof window !== 'undefined'
      && !window.location.pathname.startsWith(LOGIN_PATH)
    ) {
      window.location.assign(LOGIN_PATH)
    }
    throw new ApiError(response, body)
  }
  return body as T
}
