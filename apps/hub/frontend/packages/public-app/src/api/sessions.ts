import { apiFetch } from './client'

export interface SessionMember {
  agent_name: string
  role: string
  status: string
  status_text?: string
  current_task?: string
  current_task_from?: string
  current_task_at?: string
  last_message_at?: string
  last_seen_at?: string
  joined_at?: string
  last_action?: string
  pending_count?: number
  heartbeat_age_seconds?: number
  heartbeat_state?: string
  delivery_mode?: string
  provider?: string
  workspace_path?: string
  current_run?: RunInfo
  last_run?: RunInfo
}

export interface RunInfo {
  outcome?: string
  summary?: string
  started_at?: string
  finished_at?: string
}

export interface SessionEvent {
  event: string
  actor?: string
  target?: string
  detail?: string
  ts?: string
  payload_preview?: string
  action?: string
  message_action?: string
  delivery?: string
  delivery_mode?: string
  extra?: {
    summary?: string
    log_preview?: string
    [key: string]: unknown
  }
  [key: string]: unknown
}

export interface SessionSummary {
  member_count?: number
  pending_total?: number
  last_event_at?: string
}

export interface SessionDetailPayload {
  session_id: string
  title?: string
  project?: string
  created_by?: string
  created_at?: string
  join_code?: string
  hub_http?: string
  hub_ws?: string
  official_hub_http?: string
  members: SessionMember[]
  history: SessionEvent[]
  summary?: SessionSummary
  connected_agents?: string[]
}

export interface SessionDetailResponse {
  session: SessionDetailPayload
}

export interface FetchSessionParams {
  sessionId: string
  agentName?: string
  memberToken?: string
  adminToken?: string
}

export async function fetchSessionDetail(params: FetchSessionParams): Promise<SessionDetailPayload> {
  const qs = new URLSearchParams({ session_id: params.sessionId })
  if (params.agentName && params.memberToken) {
    qs.set('agent_name', params.agentName)
    qs.set('member_token', params.memberToken)
  }
  if (params.adminToken) qs.set('token', params.adminToken)
  const data = await apiFetch<SessionDetailResponse>(
    `/sessions/${encodeURIComponent(params.sessionId)}/detail?${qs.toString()}`
  )
  return data.session
}

export async function closeSession(sessionId: string, adminToken?: string): Promise<{ message: string }> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (adminToken) headers['X-ACP-Token'] = adminToken
  return apiFetch(`/sessions/${encodeURIComponent(sessionId)}/admin/close`, {
    method: 'POST',
    headers,
    body: '{}',
  })
}

export async function disconnectMember(
  sessionId: string,
  agentName: string,
  adminToken?: string
): Promise<{ message: string; session_closed?: boolean }> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (adminToken) headers['X-ACP-Token'] = adminToken
  return apiFetch(`/sessions/${encodeURIComponent(sessionId)}/admin/members/${encodeURIComponent(agentName)}/disconnect`, {
    method: 'POST',
    headers,
    body: '{}',
  })
}
