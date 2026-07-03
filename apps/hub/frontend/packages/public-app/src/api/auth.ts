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

export interface AuthMemberSessionParams {
  sessionId: string
  agentName: string
  memberToken: string
}

// Exchange the member token for an httpOnly session cookie. Done once; the
// cookie then authenticates the ~2s detail poll so the token never rides the
// wire again (and is never stored in JS-accessible storage).
export async function authMemberSession(params: AuthMemberSessionParams): Promise<void> {
  await apiFetch('/dashboard/session/auth', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: params.sessionId,
      agent_name: params.agentName,
      member_token: params.memberToken,
    }),
  })
}

export async function logoutMemberSession(): Promise<void> {
  await apiFetch('/dashboard/session/auth/logout', { method: 'POST' })
}
