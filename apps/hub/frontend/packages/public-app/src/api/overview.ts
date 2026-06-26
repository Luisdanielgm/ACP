import { apiFetch } from './client'

export interface MemberData {
  agent_name: string
  role: string
  status: string
  status_text?: string
  current_task?: string
  current_task_from?: string
  current_task_at?: string
  last_message_at?: string
  last_seen_at?: string
  pending_count?: number
  heartbeat_age_seconds?: number
  heartbeat_state?: string
}

export interface SessionData {
  session_id: string
  title?: string
  project?: string
  created_by?: string
  member_count: number
  pending_total: number
  last_event_at?: string
  members: MemberData[]
}

export interface OverviewData {
  session_count: number
  member_count: number
  status_counts: { idle: number; waiting: number; busy: number }
  sessions: SessionData[]
}

export interface HubFlags {
  token_required?: boolean
  storage_ready?: boolean
  auth_ready?: boolean
  migration_ready?: boolean
  auth_enforce?: boolean
  token_rotation_active?: boolean
  dashboard_sessions?: number
}

export interface TraceEvent {
  type?: string
  event?: string
  from?: string
  to?: string
  name?: string
  role?: string
  reason_code?: string
  session?: string
  session_id?: string
  ts?: string
}

export interface OverviewPayload {
  hub: HubFlags
  overview: OverviewData
  connected_agents: string[]
  traces: TraceEvent[]
}

export async function fetchOverview(): Promise<OverviewPayload> {
  return apiFetch<OverviewPayload>('/dashboard/overview')
}
