import { apiFetch } from './client'

export interface AuthSession {
  authenticated: boolean
  token_required: boolean
}

export async function fetchAuthSession(endpoint = '/dashboard/auth/session'): Promise<AuthSession> {
  return apiFetch<AuthSession>(endpoint)
}

export async function loginDashboard(token: string): Promise<void> {
  await apiFetch('/dashboard/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  })
}

export async function logoutDashboard(): Promise<void> {
  await apiFetch('/dashboard/auth/logout', { method: 'POST' })
}
