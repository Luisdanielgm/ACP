import type { MemberData, TraceEvent } from '../api/overview'

export function timeAgo(isoStr: string | undefined, lang: string): string {
  if (!isoStr || isoStr === '-') return '-'
  const then = new Date(isoStr).getTime()
  if (isNaN(then)) return isoStr
  const diff = Math.max(0, Date.now() - then)
  const s = Math.floor(diff / 1000)
  const m = Math.floor(s / 60)
  const h = Math.floor(m / 60)
  const d = Math.floor(h / 24)
  const es = lang === 'es'
  if (s < 5) return es ? 'ahora' : 'now'
  if (s < 60) return es ? `hace ${s}s` : `${s}s ago`
  if (m < 60) return es ? `hace ${m} min` : `${m} min ago`
  if (h < 24) return es ? `hace ${h}h` : `${h}h ago`
  if (d < 30) return es ? `hace ${d}d` : `${d}d ago`
  return isoStr.split('T')[0]
}

export function shortLabel(value: string | undefined, max = 18): string {
  const text = String(value || '-')
  return text.length > max ? `${text.slice(0, max - 1)}...` : text
}

export function roleGlyph(role: string | undefined): string {
  const r = String(role || '').toLowerCase()
  if (r === 'chief') return 'CH'
  if (r === 'planner') return 'PL'
  if (r === 'reviewer') return 'RV'
  if (r === 'admin') return 'AD'
  return 'WK'
}

export function roleTone(role: string | undefined): string {
  const r = String(role || '').toLowerCase()
  if (r === 'chief') return '#22d3ee'
  if (r === 'planner') return '#fbbf24'
  if (r === 'reviewer') return '#fb7185'
  if (r === 'admin') return '#c084fc'
  return '#34d399'
}

export function statusTone(status: string | undefined): string {
  const s = String(status || '').toLowerCase()
  if (s === 'busy') return '#f87171'
  if (s === 'waiting') return '#fbbf24'
  return '#34d399'
}

export function heartbeatAgeSeconds(member: MemberData): number | null {
  if (typeof member.heartbeat_age_seconds === 'number' && Number.isFinite(member.heartbeat_age_seconds)) {
    return Math.max(0, Math.round(member.heartbeat_age_seconds))
  }
  const parsed = Date.parse(String(member.last_seen_at || ''))
  if (Number.isNaN(parsed)) return null
  return Math.max(0, Math.round((Date.now() - parsed) / 1000))
}

export function heartbeatState(member: MemberData, connectedSet: Set<string> = new Set()): string {
  if (connectedSet.has(member.agent_name)) return 'live'
  const provided = String(member.heartbeat_state || '').toLowerCase()
  if (['live', 'quiet', 'stale'].includes(provided)) return provided
  const age = heartbeatAgeSeconds(member)
  if (age === null) return 'unknown'
  if (age <= 90) return 'live'
  if (age <= 360) return 'quiet'
  return 'stale'
}

export function memberIssues(member: MemberData, connectedSet: Set<string> = new Set()): string[] {
  const issues: string[] = []
  const hb = heartbeatState(member, connectedSet)
  const pending = Number(member.pending_count || 0)
  const status = String(member.status || '').toLowerCase()
  const text = `${member.status_text || ''} ${member.current_task || ''}`.toLowerCase()
  if (hb === 'stale') issues.push('heartbeat')
  if (pending >= 3) issues.push('backlog')
  else if (pending > 0 && status === 'waiting') issues.push('waiting')
  if (['error', 'failed', 'disconnect', 'closed', 'timeout'].some(n => text.includes(n))) issues.push('error')
  return [...new Set(issues)]
}

export type TrafficLevel = 'low' | 'medium' | 'high' | 'critical'

export function recentTraceSnapshot(traces: TraceEvent[]): { count: number; level: TrafficLevel } {
  const recent = traces.filter(e => {
    const parsed = Date.parse(String(e.ts || ''))
    return !Number.isNaN(parsed) && (Date.now() - parsed) <= 20000
  })
  const count = recent.length
  let level: TrafficLevel = 'low'
  if (count >= 18) level = 'critical'
  else if (count >= 10) level = 'high'
  else if (count >= 5) level = 'medium'
  return { count, level }
}

export interface TaskLaneItem {
  session_id: string
  session_label: string
  agent_name: string
  role: string
  status: string
  pending_count: number
  current_task?: string
  current_task_from?: string
  current_task_at?: string
  last_message_at?: string
}

export function collectTaskLane(sessions: { session_id: string; title?: string; project?: string; members: MemberData[] }[]): TaskLaneItem[] {
  const items: (TaskLaneItem & { priority: number })[] = []
  for (const session of sessions) {
    for (const member of session.members || []) {
      const priority = (member.pending_count || 0) * 10
        + (String(member.status || '').toLowerCase() === 'busy' ? 8 : 0)
        + (String(member.status || '').toLowerCase() === 'waiting' ? 5 : 0)
        + (member.current_task ? 4 : 0)
      if (!priority) continue
      items.push({
        session_id: session.session_id,
        session_label: session.title || session.project || session.session_id,
        agent_name: member.agent_name,
        role: member.role,
        status: member.status,
        pending_count: member.pending_count || 0,
        current_task: member.current_task,
        current_task_from: member.current_task_from,
        current_task_at: member.current_task_at,
        last_message_at: member.last_message_at,
        priority,
      })
    }
  }
  return items
    .sort((a, b) => {
      if (b.priority !== a.priority) return b.priority - a.priority
      const bt = new Date(b.current_task_at || b.last_message_at || '0').getTime()
      const at = new Date(a.current_task_at || a.last_message_at || '0').getTime()
      return bt - at
    })
    .slice(0, 6)
}
