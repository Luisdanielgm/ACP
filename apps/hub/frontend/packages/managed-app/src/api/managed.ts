import { apiFetch } from './client'

// ── Types ──

export interface ManagedUser {
  email: string
  role: string
  status: string
  expires_at?: number
  authenticated?: boolean
}

export interface Workspace {
  workspace_id: string
  name: string
  slug: string
  status: string
  admin_email?: string
  created_by?: string
}

export interface WorkspaceMembership {
  email: string
  role: string
  workspace_id: string
}

export interface AgentToken {
  token_id: string
  workspace_id: string
  agent_name: string | null
  token_hint?: string
  status: string
  created_at?: string
  last_used_at?: string
}

export interface WorkspaceSession {
  session_id: string
  workspace_id: string
  created_by_email: string
  owner_agent_name: string
  owner_member_token?: string
  title?: string
  project?: string
  prompt?: string | null
  created_at: string
  // Live coordination state. "active" when the session is currently held by
  // the coordination service; "closed" when only the persisted record exists.
  // May be omitted by older backends — treat absence as unknown.
  live_status?: 'active' | 'closed'
  member_count?: number | null
  status_counts?: Record<string, number>
}

export interface Invitation {
  invitation_id: string
  email: string
  workspace_id: string
  status: string
  accepted_at?: number
  token?: string
}

export interface ManagedAgentBootstrap {
  hub_http: string
  hub_ws: string
  requires_workspace_slug: boolean
  workspace: Workspace
  agent_token: AgentToken
  token_scope: string
  bootstrap_url: string
  managed_routes: {
    sessions: string
    session_detail_template: string
    session_join_template: string
  }
  command_examples: {
    managed_sessions: string
    managed_start: string
    managed_join: string
  }
  share_prompt: string
}

// ── Auth ──

export async function login(email: string, password: string) {
  return apiFetch<{ status: string; email: string; role: string; expires_at: number }>('/managed/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
}

export async function fetchMe() {
  const payload = await apiFetch<ManagedUser & { authenticated?: boolean }>('/managed/auth/me')
  if (payload.authenticated === false) return null
  return payload
}

export async function logout() {
  return apiFetch<{ status: string }>('/managed/auth/logout', { method: 'POST' })
}

// ── Workspaces (user) ──

export async function fetchMyWorkspaces() {
  return apiFetch<{
    workspaces: { workspace: Workspace; membership: WorkspaceMembership; sessions: WorkspaceSession[] }[]
    count: number
  }>('/managed/workspaces')
}

export async function fetchWorkspaceDetail(slug: string) {
  return apiFetch<{
    workspace: Workspace
    workspace_admin: WorkspaceMembership | null
    viewer_membership: WorkspaceMembership | null
    active_token: AgentToken | null
    invitations: Invitation[]
    sessions: WorkspaceSession[]
    counts: { sessions: number; pending_invitations: number }
  }>(`/managed/workspaces/${encodeURIComponent(slug)}`)
}

// ── Workspaces (admin) ──

export async function fetchAdminWorkspaces() {
  return apiFetch<{
    workspaces: { workspace: Workspace; workspace_admin: WorkspaceMembership | null; invitations: Invitation[] }[]
    count: number
  }>('/managed/admin/workspaces')
}

export async function createWorkspace(payload: string | { name: string; slug?: string; status?: string; admin_email?: string }) {
  const body = typeof payload === 'string' ? { name: payload } : payload
  return apiFetch<{
    status: string
    workspace: Workspace
    workspace_admin: WorkspaceMembership | null
    invitation: Invitation | null
    invitation_url: string | null
    admin_assignment: 'self_assigned' | 'invited' | 'unassigned'
  }>('/managed/admin/workspaces', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function updateWorkspace(slug: string, data: { name?: string; status?: string }) {
  return apiFetch<{ status: string; workspace: Workspace }>(`/managed/admin/workspaces/${encodeURIComponent(slug)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function deleteWorkspace(slug: string) {
  return apiFetch<{ status: string; workspace_id: string; slug: string }>(`/managed/admin/workspaces/${encodeURIComponent(slug)}`, {
    method: 'DELETE',
  })
}

export async function disableWorkspace(slug: string) {
  return apiFetch<{ status: string; workspace: Workspace }>(`/managed/admin/workspaces/${encodeURIComponent(slug)}/disable`, {
    method: 'POST',
  })
}

export async function inviteWorkspaceAdmin(slug: string, email: string) {
  return apiFetch<{ status: string; workspace: Workspace; invitation: Invitation; invitation_url: string }>(`/managed/admin/workspaces/${encodeURIComponent(slug)}/invite-admin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
}

// ── Agent Tokens ──

export async function fetchAgentTokens(slug: string) {
  return apiFetch<{ workspace: Workspace; agent_tokens: AgentToken[]; count: number }>(`/managed/admin/workspaces/${encodeURIComponent(slug)}/agent-tokens`)
}

export async function createAgentToken(slug: string, agentName: string) {
  return apiFetch<{ status: string; workspace: Workspace; agent_token: AgentToken; raw_token: string; bootstrap: ManagedAgentBootstrap }>(`/managed/admin/workspaces/${encodeURIComponent(slug)}/agent-tokens`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_name: agentName }),
  })
}

export async function revokeAgentToken(slug: string, tokenId: string) {
  return apiFetch<{ status: string; workspace: Workspace; agent_token: AgentToken }>(`/managed/admin/workspaces/${encodeURIComponent(slug)}/agent-tokens/${encodeURIComponent(tokenId)}`, {
    method: 'DELETE',
  })
}

// ── Workspace Token ──

export async function rotateWorkspaceToken(slug: string) {
  return apiFetch<{ status: string; workspace: Workspace; agent_token: AgentToken; raw_token: string; bootstrap: ManagedAgentBootstrap }>(`/managed/workspaces/${encodeURIComponent(slug)}/token/rotate`, {
    method: 'POST',
  })
}

export async function revokeWorkspaceToken(slug: string) {
  return apiFetch<{ status: string; workspace: Workspace; agent_token: AgentToken }>(`/managed/workspaces/${encodeURIComponent(slug)}/token/revoke`, {
    method: 'POST',
  })
}

// ── Sessions ──

export async function fetchWorkspaceSessions(slug: string) {
  return apiFetch<{ workspace: Workspace; sessions: WorkspaceSession[]; count: number }>(`/managed/workspaces/${encodeURIComponent(slug)}/sessions`)
}

export async function createWorkspaceSession(slug: string, data: { agent_name: string; title?: string; project?: string; prompt?: string }) {
  return apiFetch<{ status: string; workspace: Workspace; workspace_session: WorkspaceSession; acp_session: any }>(`/managed/workspaces/${encodeURIComponent(slug)}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function fetchSessionDetail(slug: string, sessionId: string) {
  return apiFetch<{ workspace: Workspace; workspace_session: WorkspaceSession; acp_session: any | null }>(`/managed/workspaces/${encodeURIComponent(slug)}/sessions/${encodeURIComponent(sessionId)}`)
}

// ── Invitations ──

export interface InvitationPreview {
  status: string
  requires_password: boolean
  workspace: { slug: string; name: string }
}

export async function fetchInvitationPreview(token: string): Promise<InvitationPreview> {
  return apiFetch<InvitationPreview>(`/managed/invitations/${encodeURIComponent(token)}/preview`)
}

export async function acceptInvitation(token: string, password?: string) {
  return apiFetch<{
    status: string
    workspace: Workspace
    invitation: Invitation
    principal: ManagedUser
    redirect_url: string
  }>(`/managed/invitations/${encodeURIComponent(token)}/accept`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password: password || null }),
  })
}

// ── Presets ──

export async function createTeamPreset(slug: string, presetId: string) {
  return apiFetch<any>(`/managed/admin/workspaces/${encodeURIComponent(slug)}/presets/create`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ preset_id: presetId }),
  })
}
