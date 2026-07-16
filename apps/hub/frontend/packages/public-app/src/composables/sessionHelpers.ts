import type { SessionMember, SessionEvent, SessionDetailPayload } from '../api/sessions'
import { AVATAR_LEADER, AVATAR_HUMAN, ROBOT_AVATAR_IDS } from '../assets/acp/acpAssets'

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
  if (r === 'chief') return '#EF9F27'
  if (r === 'collaborator') return '#1D9E75'
  return '#85B7EB'
}

// Identity initials from the agent name (first + last meaningful segment),
// skipping hex hash suffixes — so two collaborators don't both read "CO".
export function nameInitials(name: string): string {
  const parts = String(name || '')
    .split(/[-_.\s]+/)
    .filter(Boolean)
    .filter(part => !/^[0-9a-f]{6,}$/i.test(part))
  if (!parts.length) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

export function isWebOperator(name: string | undefined): boolean {
  return String(name || '').startsWith('web-operator-')
}

// Human-legible display name: strip the shared prefix and hex hash suffixes,
// then title-case what remains ("people_manager-6a2b15e1" -> "People Manager").
// The FULL agent name stays available in tooltips and detail views.
export function humanizeAgentName(name: string, prefix = ''): string {
  const raw = String(name || '')
  const rest = prefix && raw.startsWith(prefix) && raw.length > prefix.length ? raw.slice(prefix.length) : raw
  const parts = rest
    .split(/[-_.\s]+/)
    .filter(Boolean)
    .filter(part => !/^[0-9a-f]{6,}$/i.test(part))
  if (!parts.length) return raw
  return parts.map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}

// Display names for a whole roster. Token-based (not raw prefix) because real
// fleets drift in spelling: "acme-air-chief" + "acmecorp-air-people_manager"
// share the token "air" but no usable string prefix. Drops tokens present in
// EVERY name, then leading brand tokens that only differ in spelling, so the
// distinctive part ("Chief", "People Manager") is what humans read.
export function agentDisplayNames(names: string[]): Map<string, string> {
  const map = new Map<string, string>()
  const tokenized = names.filter(Boolean).map(name => ({
    name,
    tokens: name
      .split(/[-_.\s]+/)
      .filter(Boolean)
      .filter(part => !/^[0-9a-f]{6,}$/i.test(part)),
  }))
  if (!tokenized.length) return map

  let common = new Set(tokenized[0].tokens.map(t => t.toLowerCase()))
  for (const { tokens } of tokenized.slice(1)) {
    const mine = new Set(tokens.map(t => t.toLowerCase()))
    common = new Set([...common].filter(t => mine.has(t)))
  }
  if (tokenized.length < 2) common = new Set()

  let remaining = tokenized.map(({ name, tokens }) => {
    const kept = tokens.filter(t => !common.has(t.toLowerCase()))
    // Never drop a name to zero tokens: keep at least the last one.
    return { name, tokens: kept.length ? kept : tokens.slice(-1) }
  })

  // Leading brand tokens that vary in spelling ("aero" vs "aerocorp") still
  // share a long string prefix across every member — drop those too.
  if (remaining.length >= 2 && remaining.every(r => r.tokens.length >= 2)) {
    const firsts = remaining.map(r => r.tokens[0].toLowerCase())
    let shared = firsts[0]
    for (const f of firsts.slice(1)) {
      let i = 0
      while (i < shared.length && i < f.length && shared[i] === f[i]) i++
      shared = shared.slice(0, i)
    }
    if (shared.length >= 4) {
      remaining = remaining.map(r => ({ name: r.name, tokens: r.tokens.slice(1) }))
    }
  }

  for (const { name, tokens } of remaining) {
    const parts = tokens.length ? tokens : [name]
    map.set(name, parts.map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' '))
  }
  // Two members must never collapse onto the same label, and a label that
  // shrank to almost nothing ("A") reads worse than the full name — fall back
  // to the full humanized name in both cases.
  const counts = new Map<string, number>()
  for (const v of map.values()) counts.set(v, (counts.get(v) || 0) + 1)
  for (const [name, label] of map) {
    if ((counts.get(label) || 0) > 1 || label.length < 3) map.set(name, humanizeAgentName(name))
  }
  return map
}

export function statusTone(status: string | undefined): string {
  const s = String(status || '').toLowerCase()
  if (s === 'busy') return '#F0997B'
  if (s === 'waiting') return '#EF9F27'
  return '#5DCAA5'
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
  if (level === 'high') return '#F0997B'
  if (level === 'medium') return '#EF9F27'
  if (level === 'low') return '#AFA9EC'
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
  // Map route strokes read better one ramp-stop deeper than the chip tints.
  const a = String(action || '').toUpperCase()
  if (a === 'TASK') return '#EF9F27'
  if (a === 'REPLY') return '#7F77DD'
  if (a === 'INFO') return '#378ADD'
  return '#a1a1aa'
}

export function actionSoft(action: string): string {
  const a = String(action || '').toUpperCase()
  if (a === 'TASK') return 'rgba(239,159,39,0.12)'
  if (a === 'REPLY') return 'rgba(175,169,236,0.12)'
  if (a === 'INFO') return 'rgba(133,183,235,0.12)'
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

const RECENT_HISTORY_SCAN_LIMIT = 200

export function recentMemberActivity(payload: SessionDetailPayload, windowSeconds = 18): Map<string, MemberActivityData> {
  const map = new Map<string, MemberActivityData>()
  const now = Date.now()
  const history = (payload.history || []).slice(-RECENT_HISTORY_SCAN_LIMIT)

  for (const event of history) {
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
  return (payload.history || []).slice(-RECENT_HISTORY_SCAN_LIMIT).filter(e => {
    const ev = String(e.event || '').toUpperCase()
    if (ev !== 'MESSAGE_SENT' && ev !== 'MESSAGE_DELIVERED') return false
    const ts = Date.parse(String(e.ts || ''))
    return !Number.isNaN(ts) && (now - ts) <= windowMs
  })
}

// ── Asset selectors (state → visual, driven by real data) ──

// Keyword → themed avatar id. Matched against the agent name so a "finance"
// agent shows the finance portrait. This is a display heuristic over the real
// name — NOT a domain-role field (we only track chief/collaborator/member).
// Order matters: earlier, more specific keywords win.
const DOMAIN_AVATAR_MATCHERS: Array<[RegExp, string]> = [
  [/front[\s_-]?end|frontend|\bfe\b/i, 'frontend-developer'],
  [/back[\s_-]?end|backend|\bbe\b/i, 'backend-developer'],
  [/dev[\s_-]?ops|devops|sre|infra|platform/i, 'devops-engineer'],
  [/\bqa\b|quality|tester|testing/i, 'quality-assurance'],
  [/security|cyber|infosec|\bsec\b/i, 'cybersecurity'],
  [/\bux\b|\bui\b|ux[\s_-]?ui|design/i, 'ux-ui-designer'],
  [/\bdata\b|analytics|data[\s_-]?scien/i, 'data-analyst'],
  [/research|knowledge|\bdocs?\b|librarian/i, 'research-knowledge'],
  [/legal|compliance|counsel/i, 'legal-compliance'],
  [/logistic|supply|warehouse|fulfil/i, 'logistics'],
  [/customer[\s_-]?success|\bcs\b|success/i, 'customer-success'],
  [/market|growth|seo|content/i, 'marketing'],
  [/sales|revenue|account[\s_-]?exec|\bae\b/i, 'sales'],
  [/product|\bpm\b|roadmap/i, 'product-manager'],
  [/financ|finance|accounting|treasur|billing|payment/i, 'finance'],
  [/operation|\bops\b/i, 'operations'],
  [/human[\s_-]?resource|people|\bhr\b|rrhh|recruit|talent/i, 'human-resources'],
  [/support|soporte|help[\s_-]?desk|service[\s_-]?desk/i, 'support'],
]

// Stable avatar per member: chief gets the leader portrait, the human operator gets the
// human portrait, agents whose name matches a domain keyword get the themed portrait,
// and everyone else hashes their name onto a consistent robot face.
export function avatarForMember(member: SessionMember): string {
  if (normalizedRole(member.role) === 'chief') return AVATAR_LEADER
  if (isWebOperator(member.agent_name)) return AVATAR_HUMAN
  const name = String(member.agent_name || '')
  for (const [pattern, id] of DOMAIN_AVATAR_MATCHERS) {
    if (pattern.test(name)) return id
  }
  const pool = ROBOT_AVATAR_IDS
  if (!pool.length) return AVATAR_LEADER
  return pool[hashValue(name) % pool.length]
}

export type LinkFreshness = 'current' | 'recent' | 'old' | 'expired'

// Relationship recency thresholds mirror the reference legend:
// current < 30s, recent 30s–2m, old 2m–5m, expired > 5m.
export function linkFreshness(ageSeconds: number | null): LinkFreshness {
  if (ageSeconds === null || ageSeconds > 300) return 'expired'
  if (ageSeconds <= 30) return 'current'
  if (ageSeconds <= 120) return 'recent'
  return 'old'
}

export type HeartbeatTier = 'strong' | 'normal' | 'weak' | 'none'

export function heartbeatTier(member: SessionMember, connectedSet: Set<string> = new Set()): HeartbeatTier {
  const state = heartbeatState(member, connectedSet)
  if (state === 'live') {
    const age = heartbeatAgeSeconds(member)
    return connectedSet.has(member.agent_name) && (age === null || age <= 30) ? 'strong' : 'normal'
  }
  if (state === 'quiet') return 'weak'
  return 'none'
}

export function heartbeatIconName(tier: HeartbeatTier): string {
  return `heartbeat-${tier}`
}

// Presence badge — we track online/silent/disconnected (the kit's "thinking" state is not
// something the protocol reports, so it is intentionally never selected).
export function presenceIconName(member: SessionMember, connectedSet: Set<string> = new Set()): string {
  const state = heartbeatState(member, connectedSet)
  if (state === 'live') return 'presence-online'
  if (state === 'quiet') return 'presence-silent'
  return 'presence-disconnected'
}

// Operational badge — maps our operational state (+ real pending backlog) to a kit icon.
export function operationIconName(op: OperationalState, pending = 0): string {
  if (op.tone === 'warning') return 'operation-incident'
  if (pending >= 3) return 'operation-queue-high'
  if (op.tone === 'working') return 'operation-working'
  if (op.tone === 'alert') return 'operation-processing'
  if (op.tone === 'listening') return 'operation-waiting'
  return 'operation-idle'
}

// Message-type icon from an event.
export function messageIconNameForEvent(event: SessionEvent): string {
  const ev = String(event.event || '').toUpperCase()
  const detail = String(event.detail || '').toLowerCase()
  if (['error', 'failed', 'rejected'].some(n => detail.includes(n))) return 'message-error'
  if (ev === 'HEARTBEAT') return 'message-heartbeat'
  if (String(event.target || '').toLowerCase() === 'all' || String(event.target || '') === '*') return 'message-broadcast'
  const action = messageActionType(event)
  if (action === 'TASK') return 'message-task'
  if (action === 'INFO') return 'message-information'
  if (action === 'REPLY') return 'message-response'
  if (['SESSION_CREATED', 'SESSION_JOINED', 'SESSION_LEFT', 'SESSION_CLOSED', 'STATUS_UPDATED'].includes(ev)) return 'message-system'
  return 'message-system'
}

// Result/outcome icon — delivery + event type, no read-receipt invention.
export function resultIconNameForEvent(event: SessionEvent): string {
  const ev = String(event.event || '').toUpperCase()
  const detail = String(event.detail || '').toLowerCase()
  if (ev === 'WAIT_TIMEOUT' || ['error', 'failed', 'rejected', 'timeout'].some(n => detail.includes(n))) return 'result-rejected'
  if (['RUN_FINISHED', 'RUN_REPLY_SENT'].includes(ev)) return 'result-completed'
  const delivery = deliveryMode(event)
  if (delivery === 'queued') return 'result-pending'
  if (delivery === 'immediate' || delivery === 'dequeued') return 'result-delivered'
  return 'result-delivered'
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
  if (['MESSAGE_SENT', 'MESSAGE_DELIVERED', 'WALL_POSTED'].includes(v)) return 'message'
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
  const count = (payload.history || []).slice(-RECENT_HISTORY_SCAN_LIMIT).filter(e => {
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

export { buildInvitePrompt, hubOriginForInvite, hubWsForInvite } from './invitePrompt'
