import type { SessionMember, SessionEvent, SessionDetailPayload } from '../api/sessions'

// ── Roles ──

export function normalizedRole(value: string | undefined): string {
  const r = String(value || '').toLowerCase()
  if (r === 'chief') return 'chief'
  if (r === 'collaborator') return 'collaborator'
  return 'member'
}

export function roleGlyph(role: string | undefined): string {
  const r = normalizedRole(role)
  if (r === 'chief') return 'CH'
  if (r === 'collaborator') return 'CO'
  return 'AG'
}

export function roleIcon(role: string | undefined): string {
  const r = normalizedRole(role)
  if (r === 'chief') return '♛'
  if (r === 'collaborator') return '🤝'
  return '•'
}

export function roleTone(role: string | undefined): string {
  const r = normalizedRole(role)
  if (r === 'chief') return '#facc15'
  if (r === 'collaborator') return '#818cf8'
  return '#22d3ee'
}

export function statusTone(status: string | undefined): string {
  const s = String(status || '').toLowerCase()
  if (s === 'busy') return '#f87171'
  if (s === 'waiting') return '#fbbf24'
  return '#34d399'
}

// ── Heartbeat ──

export function heartbeatAgeSeconds(member: SessionMember): number | null {
  if (typeof member.heartbeat_age_seconds === 'number' && Number.isFinite(member.heartbeat_age_seconds)) {
    return Math.max(0, Math.round(member.heartbeat_age_seconds))
  }
  const parsed = Date.parse(String(member.last_seen_at || ''))
  if (Number.isNaN(parsed)) return null
  return Math.max(0, Math.round((Date.now() - parsed) / 1000))
}

export function heartbeatState(member: SessionMember, connectedSet: Set<string> = new Set()): string {
  if (connectedSet.has(member.agent_name)) return 'live'
  const provided = String(member.heartbeat_state || '').toLowerCase()
  if (['live', 'quiet', 'stale'].includes(provided)) return provided
  const age = heartbeatAgeSeconds(member)
  if (age === null) return 'unknown'
  if (age <= 90) return 'live'
  if (age <= 360) return 'quiet'
  return 'stale'
}

// ── Issues ──

export interface Issue {
  key: string
  label: string
  level: 'low' | 'medium' | 'high'
}

export function memberIssues(member: SessionMember, connectedSet: Set<string> = new Set()): Issue[] {
  const issues: Issue[] = []
  const hb = heartbeatState(member, connectedSet)
  const pending = Number(member.pending_count || 0)
  const status = String(member.status || '').toLowerCase()
  const text = `${member.status_text || ''} ${member.current_task || ''}`.toLowerCase()

  if (hb === 'stale') issues.push({ key: 'heartbeat', label: 'issue_stale_heartbeat', level: 'high' })
  if (pending >= 3) issues.push({ key: 'backlog', label: 'issue_backlog_high', level: 'medium' })
  else if (pending > 0 && status === 'waiting') issues.push({ key: 'waiting', label: 'issue_backlog_waiting', level: 'low' })
  if (['error', 'failed', 'disconnect', 'closed', 'timeout'].some(n => text.includes(n)))
    issues.push({ key: 'error', label: 'issue_error_state', level: 'high' })

  return issues
}

export function eventIssues(event: SessionEvent, membersByName: Map<string, SessionMember> = new Map()): Issue[] {
  const issues: Issue[] = []
  const ev = String(event.event || '').toUpperCase()
  const detail = String(event.detail || '').toLowerCase()

  if (ev === 'WAIT_TIMEOUT') issues.push({ key: 'timeout', label: 'issue_recent_timeout', level: 'medium' })
  if (ev === 'MESSAGE_DELIVERED' && String(event.delivery || event.delivery_mode || '').toLowerCase() === 'queued')
    issues.push({ key: 'queued', label: 'issue_recent_queue', level: 'low' })

  const actor = event.actor ? membersByName.get(event.actor) : undefined
  if (actor) {
    const mi = memberIssues(actor)
    for (const issue of mi) {
      if (!issues.some(i => i.key === issue.key)) issues.push(issue)
    }
  }

  return issues
}

export function maxIssueLevel(issues: Issue[]): string {
  if (issues.some(i => i.level === 'high')) return 'high'
  if (issues.some(i => i.level === 'medium')) return 'medium'
  if (issues.some(i => i.level === 'low')) return 'low'
  return ''
}

export function primaryIssueLabel(issues: Issue[]): string {
  return issues[0]?.label || ''
}

export function issueAccent(level: string): string {
  if (level === 'high') return '#f87171'
  if (level === 'medium') return '#fbbf24'
  if (level === 'low') return '#c084fc'
  return 'transparent'
}

// ── Message actions ──

export function normalizeMessageAction(value: string | undefined): string {
  const v = String(value || '').toUpperCase()
  if (['TASK', 'INFO', 'REPLY'].includes(v)) return v
  return ''
}

export function messageActionType(event: SessionEvent): string {
  return normalizeMessageAction(event.action || event.message_action || (event.extra as any)?.action)
}

export function normalizeDeliveryMode(value: string | undefined): string {
  const v = String(value || '').toLowerCase()
  if (['immediate', 'queued', 'dequeued'].includes(v)) return v
  return ''
}

export function deliveryMode(event: SessionEvent): string {
  return normalizeDeliveryMode(event.delivery || event.delivery_mode || (event.extra as any)?.delivery)
}

export function actionTone(action: string): string {
  const a = String(action || '').toUpperCase()
  if (a === 'TASK') return '#fbbf24'
  if (a === 'REPLY') return '#a78bfa'
  if (a === 'INFO') return '#22d3ee'
  return '#a1a1aa'
}

export function actionSoft(action: string): string {
  const a = String(action || '').toUpperCase()
  if (a === 'TASK') return 'rgba(251,191,36,0.12)'
  if (a === 'REPLY') return 'rgba(167,139,250,0.12)'
  if (a === 'INFO') return 'rgba(34,211,238,0.12)'
  return 'rgba(161,161,170,0.08)'
}

export function actionChipClass(action: string): string {
  const a = String(action || '').toUpperCase()
  if (['TASK', 'INFO', 'REPLY'].includes(a)) return a.toLowerCase()
  return ''
}

export function actionGlyph(action: string): string {
  const a = String(action || '').toUpperCase()
  if (a === 'TASK') return 'T'
  if (a === 'REPLY') return 'R'
  if (a === 'INFO') return 'I'
  return '?'
}

export function deliveryClass(mode: string): string {
  const m = normalizeDeliveryMode(mode)
  return m || ''
}

export function floatTagLabel(action: string, delivery: string): string {
  const a = actionGlyph(action)
  const d = normalizeDeliveryMode(delivery)
  if (d === 'queued') return `Q:${a}`
  if (d === 'dequeued') return `D:${a}`
  return `+${a}`
}

// ── Activity ──

export interface DeliveryCounts {
  immediate: number
  queued: number
  dequeued: number
}

export interface ActionDeliveryCounts {
  TASK: DeliveryCounts
  INFO: DeliveryCounts
  REPLY: DeliveryCounts
}

export interface MemberActivityData {
  hasOutgoing: boolean
  hasIncoming: boolean
  isBusy: boolean
  sentTotal: number
  receivedTotal: number
  lastActionType: string
  sent: ActionDeliveryCounts
  received: ActionDeliveryCounts
}

function emptyDeliveryCounts(): DeliveryCounts {
  return { immediate: 0, queued: 0, dequeued: 0 }
}

function emptyActionDeliveryCounts(): ActionDeliveryCounts {
  return { TASK: emptyDeliveryCounts(), INFO: emptyDeliveryCounts(), REPLY: emptyDeliveryCounts() }
}

export function recentMemberActivity(payload: SessionDetailPayload, windowSeconds = 18): Map<string, MemberActivityData> {
  const map = new Map<string, MemberActivityData>()
  const now = Date.now()

  for (const event of payload.history || []) {
    const ev = String(event.event || '').toUpperCase()
    if (ev !== 'MESSAGE_SENT' && ev !== 'MESSAGE_DELIVERED') continue
    const ts = Date.parse(String(event.ts || ''))
    if (Number.isNaN(ts) || (now - ts) > windowSeconds * 1000) continue

    const action = messageActionType(event)
    if (!action) continue
    const del = deliveryMode(event)

    const actor = String(event.actor || '')
    const target = String(event.target || '')

    if (actor) {
      if (!map.has(actor)) map.set(actor, { hasOutgoing: false, hasIncoming: false, isBusy: false, sentTotal: 0, receivedTotal: 0, lastActionType: '', sent: emptyActionDeliveryCounts(), received: emptyActionDeliveryCounts() })
      const a = map.get(actor)!
      a.hasOutgoing = true
      a.sentTotal++
      a.lastActionType = action
      const bucket = a.sent[action as keyof ActionDeliveryCounts]
      if (bucket && del) (bucket as any)[del] = ((bucket as any)[del] || 0) + 1
    }

    if (target) {
      if (!map.has(target)) map.set(target, { hasOutgoing: false, hasIncoming: false, isBusy: false, sentTotal: 0, receivedTotal: 0, lastActionType: '', sent: emptyActionDeliveryCounts(), received: emptyActionDeliveryCounts() })
      const t = map.get(target)!
      t.hasIncoming = true
      t.receivedTotal++
      const bucket = t.received[action as keyof ActionDeliveryCounts]
      if (bucket && del) (bucket as any)[del] = ((bucket as any)[del] || 0) + 1
    }
  }

  for (const member of payload.members || []) {
    const status = String(member.status || '').toLowerCase()
    if (status === 'busy') {
      if (!map.has(member.agent_name)) map.set(member.agent_name, { hasOutgoing: false, hasIncoming: false, isBusy: false, sentTotal: 0, receivedTotal: 0, lastActionType: '', sent: emptyActionDeliveryCounts(), received: emptyActionDeliveryCounts() })
      map.get(member.agent_name)!.isBusy = true
    }
  }

  return map
}

export function memberActivity(member: SessionMember, activityMap: Map<string, MemberActivityData>): MemberActivityData {
  return activityMap.get(member.agent_name) || {
    hasOutgoing: false, hasIncoming: false, isBusy: false,
    sentTotal: 0, receivedTotal: 0, lastActionType: '',
    sent: emptyActionDeliveryCounts(), received: emptyActionDeliveryCounts(),
  }
}

export interface OperationalState {
  key: string
  tone: string
}

export function memberOperationalState(member: SessionMember, activity: MemberActivityData, issues: Issue[] = []): OperationalState {
  if (issues.some(i => i.level === 'high')) return { key: 'op_state_warning', tone: 'warning' }
  if (activity.isBusy) return { key: 'op_state_working', tone: 'working' }
  if (activity.hasOutgoing || activity.hasIncoming) return { key: 'op_state_alert', tone: 'alert' }
  const status = String(member.status || '').toLowerCase()
  if (status === 'waiting') return { key: 'op_state_listening', tone: 'listening' }
  return { key: 'op_state_idle', tone: 'idle' }
}

// ── Squad map ──

export function mapRoutePath(
  from: { x: number; y: number },
  to: { x: number; y: number },
  seed = 0
): string {
  const dx = to.x - from.x
  const dy = to.y - from.y
  const dist = Math.sqrt(dx * dx + dy * dy)
  const bend = Math.max(28, dist * 0.25) * (seed % 2 === 0 ? 1 : -1)
  const mx = (from.x + to.x) / 2
  const my = (from.y + to.y) / 2
  const nx = -dy / (dist || 1)
  const ny = dx / (dist || 1)
  const cx = mx + nx * bend
  const cy = my + ny * bend
  return `M${from.x},${from.y} Q${cx},${cy} ${to.x},${to.y}`
}

export function mapAnimationEvents(payload: SessionDetailPayload, windowMs = 6000): SessionEvent[] {
  const now = Date.now()
  return (payload.history || []).filter(e => {
    const ev = String(e.event || '').toUpperCase()
    if (ev !== 'MESSAGE_SENT' && ev !== 'MESSAGE_DELIVERED') return false
    const ts = Date.parse(String(e.ts || ''))
    return !Number.isNaN(ts) && (now - ts) <= windowMs
  })
}

// ── Sorting ──

const ROLE_PRIORITY: Record<string, number> = { chief: 0, collaborator: 1, member: 2 }

export function sortedMembers(payload: SessionDetailPayload): SessionMember[] {
  return [...(payload.members || [])].sort((a, b) => {
    const ra = ROLE_PRIORITY[normalizedRole(a.role)] ?? 3
    const rb = ROLE_PRIORITY[normalizedRole(b.role)] ?? 3
    if (ra !== rb) return ra - rb
    return (a.agent_name || '').localeCompare(b.agent_name || '')
  })
}

// ── Colors ──

export function hashValue(value: string): number {
  let h = 0
  for (let i = 0; i < value.length; i++) {
    h = ((h << 5) - h + value.charCodeAt(i)) | 0
  }
  return Math.abs(h)
}

export interface MemberPalette {
  accent: string
  soft: string
  glow: string
}

export function memberPalette(member: SessionMember): MemberPalette {
  const base = roleTone(member.role)
  const hue = hashValue(member.agent_name || '') % 360
  return {
    accent: base,
    soft: `hsla(${hue}, 60%, 50%, 0.12)`,
    glow: `hsla(${hue}, 60%, 50%, 0.25)`,
  }
}

export function memberStyleVars(member: SessionMember): string {
  const palette = memberPalette(member)
  return `--member-accent:${palette.accent};--member-soft:${palette.soft};--member-glow:${palette.glow};`
}

// ── Event classification ──

export function eventClass(value: string | undefined): string {
  const v = String(value || '').toUpperCase()
  if (['SESSION_CREATED', 'SESSION_JOINED', 'SESSION_LEFT', 'SESSION_CLOSED'].includes(v)) return 'session'
  if (['WAIT_STARTED', 'WAIT_TIMEOUT'].includes(v)) return 'wait'
  if (['STATUS_UPDATED', 'HEARTBEAT'].includes(v)) return 'status'
  if (['MESSAGE_SENT', 'MESSAGE_DELIVERED'].includes(v)) return 'message'
  if (['RUN_STARTED', 'RUN_LOG', 'RUN_FINISHED', 'RUN_REPLY_SENT', 'RUN_INTERRUPTED'].includes(v)) return 'status'
  return 'session'
}

export function eventTouchesAgent(event: SessionEvent, agentName: string): boolean {
  return String(event.actor || '') === agentName || String(event.target || '') === agentName
}

export function isRecentActivity(ts: string | undefined, windowSeconds = 18): boolean {
  const parsed = Date.parse(String(ts || ''))
  return !Number.isNaN(parsed) && (Date.now() - parsed) <= windowSeconds * 1000
}

// ── Session health ──

export type SessionHealth = 'healthy' | 'warning' | 'critical'

export function sessionHealthState(payload: SessionDetailPayload, connectedSet: Set<string> = new Set()): SessionHealth {
  const members = payload.members || []
  let staleCount = 0
  let issueCount = 0

  for (const member of members) {
    const hb = heartbeatState(member, connectedSet)
    if (hb === 'stale') staleCount++
    if (memberIssues(member, connectedSet).length > 0) issueCount++
  }

  if (staleCount >= 2 || (members.length > 0 && staleCount === members.length)) return 'critical'
  if (issueCount > 0 || staleCount > 0) return 'warning'
  return 'healthy'
}

// ── Utility ──

export function compactPath(value: string | undefined): string {
  const v = String(value || '-')
  if (v === '-') return v
  const parts = v.replace(/\\/g, '/').split('/').filter(Boolean)
  return parts.length > 0 ? parts[parts.length - 1] : v
}

export function runSummary(run: SessionMember['current_run'] | undefined): string {
  if (!run) return '-'
  const parts: string[] = []
  if (run.outcome) parts.push(run.outcome)
  if (run.summary) parts.push(run.summary)
  return parts.join(' · ') || '-'
}

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function timeAgo(isoStr: string | undefined, lang = 'en'): string {
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

// ── Traffic ──

export type TrafficLevel = 'low' | 'medium' | 'high' | 'critical'

export function recentTrafficSnapshot(payload: SessionDetailPayload, windowMs = 20000): { count: number; level: TrafficLevel } {
  const now = Date.now()
  const count = (payload.history || []).filter(e => {
    const ts = Date.parse(String(e.ts || ''))
    return !Number.isNaN(ts) && (now - ts) <= windowMs
  }).length
  let level: TrafficLevel = 'low'
  if (count >= 18) level = 'critical'
  else if (count >= 10) level = 'high'
  else if (count >= 5) level = 'medium'
  return { count, level }
}

// ── Invite ──

export function hubOriginForInvite(payload: SessionDetailPayload): string {
  return payload.hub_http || payload.official_hub_http || ''
}

export function hubWsForInvite(payload: SessionDetailPayload): string {
  if (payload.hub_ws) return payload.hub_ws
  const http = hubOriginForInvite(payload)
  if (!http) return ''
  return http.replace(/^http/, 'ws') + '/ws'
}

export function buildInvitePrompt(payload: SessionDetailPayload, lang = 'en'): string {
  const origin = hubOriginForInvite(payload)
  const sid = payload.session_id || ''
  const join = payload.join_code || ''
  const es = lang === 'es'

  const lines: string[] = []
  if (es) {
    lines.push('# Para unirse a esta sesion ACP:')
    lines.push('')
    lines.push('# Usa un config distinto por agente; no reutilices el config del chief.')
    lines.push('python ACP_AGENT/acp.py join-session \\')
    lines.push('  --config ACP_AGENT/agents/<agent>.json \\')
    if (origin) lines.push(`  --hub-http "${origin}" \\`)
    if (join) {
      lines.push(`  --code "${join}"`)
    } else {
      lines.push('  --code "<JOIN_CODE>"')
      if (sid) lines.push(`# Session ID: ${sid}`)
    }
    lines.push('')
    lines.push('python ACP_AGENT/acp.py listen --config ACP_AGENT/agents/<agent>.json')
  } else {
    lines.push('# To join this ACP session:')
    lines.push('')
    lines.push('# Use a distinct config per agent; do not reuse the chief config.')
    lines.push('python ACP_AGENT/acp.py join-session \\')
    lines.push('  --config ACP_AGENT/agents/<agent>.json \\')
    if (origin) lines.push(`  --hub-http "${origin}" \\`)
    if (join) {
      lines.push(`  --code "${join}"`)
    } else {
      lines.push('  --code "<JOIN_CODE>"')
      if (sid) lines.push(`# Session ID: ${sid}`)
    }
    lines.push('')
    lines.push('python ACP_AGENT/acp.py listen --config ACP_AGENT/agents/<agent>.json')
  }
  return lines.join('\n')
}
