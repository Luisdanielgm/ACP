import type { MemberData, TraceEvent } from '../api/overview'
import { heartbeatState } from './sessionHelpers'

export { timeAgo, heartbeatAgeSeconds, heartbeatState, statusTone } from './sessionHelpers'

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
  if (r === 'chief') return '#85B7EB'
  if (r === 'planner') return '#EF9F27'
  if (r === 'reviewer') return '#fb7185'
  if (r === 'admin') return '#AFA9EC'
  return '#5DCAA5'
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
