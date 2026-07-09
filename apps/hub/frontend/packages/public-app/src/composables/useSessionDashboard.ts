import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchAuthSession, authMemberSession, logoutMemberSession } from '../api/auth'
import { fetchSessionDetail, closeSession, disconnectMember, type SessionDetailPayload, type SessionMember, type SessionEvent } from '../api/sessions'
import {
  sortedMembers, memberIssues, eventIssues, heartbeatState, eventClass, eventTouchesAgent,
  recentMemberActivity, memberActivity, memberOperationalState,
  recentTrafficSnapshot, sessionHealthState,
  type MemberActivityData, type Issue, type TrafficLevel, type SessionHealth,
} from './sessionHelpers'

export type AccessMode = 'member' | 'admin' | 'hybrid'
export type TimelineFilter = 'all' | 'session' | 'message' | 'wait' | 'status'

const STORAGE_KEY = 'acp_session_dashboard_access'

// Lets a host view (e.g. managed-app embedding this dashboard) supply access
// directly instead of relying on the standalone dashboard's URL query/hash/
// sessionStorage resolution. See `applyProgrammaticContext` below.
export interface DashboardContext {
  sessionId: string
  agentName?: string
  memberToken?: string
  adminToken?: string
}

export interface UseSessionDashboardOptions {
  authEndpoint?: string
  redirectPath?: string
  context?: DashboardContext
}

export function useSessionDashboard(options: UseSessionDashboardOptions = {}) {
  const authEndpoint = options.authEndpoint || '/dashboard/auth/session'
  const redirectPath = options.redirectPath || '/dashboard'
  // Captured once: a static, programmatically-supplied access context. When
  // present it takes over `loadFromQueryOrStorage` entirely (see below).
  const programmaticContext = options.context || null

  const route = useRoute()
  const router = useRouter()

  // ── Auth state ──
  const dashboardAuthenticated = ref(false)
  const dashboardTokenRequired = ref(false)

  // ── Access form ──
  const sessionIdInput = ref('')
  const agentNameInput = ref('')
  const memberTokenInput = ref('')
  const adminTokenInput = ref('')
  const accessMode = ref<AccessMode>('member')
  const accessCompact = ref(false)

  // ── Session state ──
  const payload = ref<SessionDetailPayload | null>(null)
  const loading = ref(false)
  const polling = ref(false)
  const statusMessage = ref('')
  const statusIsError = ref(false)
  const isFirstRender = ref(true)

  // ── Filters ──
  const timelineFilter = ref<TimelineFilter>('all')
  const agentFilter = ref('')
  const problemMode = ref(false)
  const showRawJson = ref(false)

  let pollHandle: ReturnType<typeof setInterval> | null = null
  let inFlight = false
  let loadRequestId = 0
  // True once the in-memory member token has been exchanged for the httpOnly
  // cookie this page load. Reset when the token changes or access is cleared.
  let memberSessionExchanged = false

  // ── Computed ──

  const connectedSet = computed(() => new Set(payload.value?.connected_agents ?? []))

  const members = computed(() => payload.value ? sortedMembers(payload.value) : [])

  const activityMap = computed(() => payload.value ? recentMemberActivity(payload.value) : new Map<string, MemberActivityData>())

  const visibleMembers = computed(() => {
    let items = members.value
    if (agentFilter.value) {
      items = items.filter(m => m.agent_name === agentFilter.value)
    }
    if (problemMode.value) {
      items = items.filter(m => memberIssues(m, connectedSet.value).length > 0)
    }
    return items
  })

  const filteredHistory = computed(() => {
    let events = payload.value?.history || []
    if (timelineFilter.value !== 'all') {
      events = events.filter(e => eventClass(e.event) === timelineFilter.value)
    }
    if (agentFilter.value) {
      events = events.filter(e => eventTouchesAgent(e, agentFilter.value))
    }
    if (problemMode.value) {
      const membersByName = new Map<string, SessionMember>(members.value.map(m => [m.agent_name, m]))
      events = events.filter(e => eventIssues(e, membersByName).length > 0)
    }
    return events
  })

  const trafficSnapshot = computed(() =>
    payload.value ? recentTrafficSnapshot(payload.value) : { count: 0, level: 'low' as TrafficLevel }
  )

  const healthState = computed<SessionHealth>(() =>
    payload.value ? sessionHealthState(payload.value, connectedSet.value) : 'healthy'
  )

  const problemSummary = computed(() => {
    const memberCount = members.value.filter(m => memberIssues(m, connectedSet.value).length > 0).length
    const membersByName = new Map<string, SessionMember>(members.value.map(m => [m.agent_name, m]))
    const eventCount = (payload.value?.history || []).filter(e => eventIssues(e, membersByName).length > 0).length
    return { memberCount, eventCount }
  })

  const adminActionsAvailable = computed(() => {
    return Boolean(adminTokenInput.value.trim() || dashboardAuthenticated.value)
  })

  // ── Status ──

  function setStatus(msg: string, isError = false) {
    statusMessage.value = msg
    statusIsError.value = isError
  }

  // ── Access persistence ──

  function persistAccess() {
    // Programmatic context is supplied fresh by the host view on every mount;
    // never stash it under this dashboard's own sessionStorage key.
    if (programmaticContext) return
    try {
      // member_token is intentionally NOT persisted: it is exchanged once for an
      // httpOnly cookie that survives reload and authenticates the poll. Only
      // non-secret session_id + agent_name (and the admin token, which still
      // authenticates via header) are stored so a reload can resume.
      const data = {
        session_id: sessionIdInput.value,
        agent_name: agentNameInput.value,
        admin_token: adminTokenInput.value,
        access_mode: accessMode.value,
      }
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data))
    } catch { /* ignore */ }
  }

  function restoreAccess() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY)
      if (!raw) return false
      const data = JSON.parse(raw)
      if (data.session_id) sessionIdInput.value = data.session_id
      if (data.agent_name) agentNameInput.value = data.agent_name
      if (data.admin_token) adminTokenInput.value = data.admin_token
      if (data.access_mode) accessMode.value = data.access_mode
      return Boolean(data.session_id)
    } catch { return false }
  }

  function clearAccess() {
    try {
      sessionStorage.removeItem(STORAGE_KEY)
    } catch { /* ignore */ }
  }

  function clearLoadedSession() {
    stopPolling()
    // Revoke the member session cookie server-side; ignore errors (admin-only
    // sessions never had one, and a failed revoke must not block teardown).
    if (memberSessionExchanged) {
      void logoutMemberSession().catch(() => { /* ignore */ })
    }
    memberSessionExchanged = false
    payload.value = null
    isFirstRender.value = true
    clearAccess()
  }

  function readMemberTokenFromHash(): string {
    if (typeof window === 'undefined') return ''
    const raw = String(window.location.hash || '').replace(/^#/, '')
    if (!raw) return ''
    try {
      const fragment = new URLSearchParams(raw)
      return String(fragment.get('member_token') || '').trim()
    } catch {
      return ''
    }
  }

  function scrubMemberTokenFromHash(): void {
    if (typeof window === 'undefined' || !window.history?.replaceState) return
    const raw = String(window.location.hash || '').replace(/^#/, '')
    if (!raw) return
    let fragment: URLSearchParams
    try {
      fragment = new URLSearchParams(raw)
    } catch {
      return
    }
    if (!fragment.has('member_token')) return
    fragment.delete('member_token')
    const remaining = fragment.toString()
    const newUrl = window.location.pathname + window.location.search + (remaining ? `#${remaining}` : '')
    window.history.replaceState(window.history.state, '', newUrl)
  }

  function applyQueryParams() {
    const q = route.query
    if (q.session_id) sessionIdInput.value = String(q.session_id)
    if (q.agent_name) agentNameInput.value = String(q.agent_name)
    // member_token is preferred via the URL fragment so it never reaches
    // server access logs or Referer headers. Fall back to the legacy query
    // form for backwards compatibility with previously shared URLs.
    const memberTokenFromHash = readMemberTokenFromHash()
    if (memberTokenFromHash) {
      memberTokenInput.value = memberTokenFromHash
      scrubMemberTokenFromHash()
    } else if (q.member_token) {
      memberTokenInput.value = String(q.member_token)
    }
    if (q.token) adminTokenInput.value = String(q.token)
  }

  function inferAccessMode(): AccessMode {
    const hasMember = Boolean(agentNameInput.value.trim() && memberTokenInput.value.trim())
    const hasAdmin = Boolean(adminTokenInput.value.trim() || dashboardAuthenticated.value)
    if (hasMember && hasAdmin) return 'hybrid'
    if (hasAdmin) return 'admin'
    return 'member'
  }

  // ── Session loading ──

  async function checkAuth() {
    try {
      const session = await fetchAuthSession(authEndpoint)
      dashboardAuthenticated.value = session.authenticated
      dashboardTokenRequired.value = session.token_required
    } catch (e: any) {
      if (e?.status === 401) {
        dashboardAuthenticated.value = false
        dashboardTokenRequired.value = false
      } else {
        setStatus(e?.message || 'auth check failed', true)
      }
    }
  }

  function redirectToAccess() {
    stopPolling()
    memberSessionExchanged = false
    router.push({ path: redirectPath, query: { notice: 'session_unavailable' } })
  }

  async function loadSession(showLoading = false): Promise<boolean> {
    if (inFlight) return false

    const sessionId = sessionIdInput.value.trim()
    if (!sessionId) {
      setStatus('', true)
      return false
    }

    const agentName = agentNameInput.value.trim()
    const memberToken = memberTokenInput.value.trim()
    const adminToken = adminTokenInput.value.trim()

    // A member is authorized either by a fresh token pending exchange, or by an
    // already-exchanged httpOnly cookie (e.g. after a reload, when no token is
    // in memory). Both count as member access.
    const hasMemberToken = Boolean(agentName && memberToken)
    const hasMemberAccess = hasMemberToken || memberSessionExchanged
    const hasAdminAccess = Boolean(adminToken || dashboardAuthenticated.value)
    if (!hasMemberAccess && !hasAdminAccess) {
      return false
    }

    if (showLoading) loading.value = true
    inFlight = true
    const requestId = ++loadRequestId

    try {
      // Exchange the member token for the cookie exactly once, before the first
      // poll. After this the token is no longer needed and is dropped from the
      // in-memory ref; the cookie authenticates every subsequent request.
      if (hasMemberToken && !memberSessionExchanged) {
        await authMemberSession({ sessionId, agentName, memberToken })
        if (requestId !== loadRequestId) return false
        memberSessionExchanged = true
        memberTokenInput.value = ''
      }

      const data = await fetchSessionDetail({
        sessionId,
        adminToken: adminToken || undefined,
      })
      if (requestId !== loadRequestId) return false
      payload.value = data
      persistAccess()
      isFirstRender.value = false
      setStatus('')
      return true
    } catch (e: any) {
      if (requestId !== loadRequestId) return false
      // 401/403: the member cookie is missing, expired, or revoked (or the token
      // exchange was rejected). 404: the session is gone. Route back to the
      // access form so the user can re-enter the token/link to re-exchange.
      if (e.status === 401 || e.status === 403 || e.status === 404) {
        redirectToAccess()
        return false
      }
      setStatus(e.message || 'request failed', true)
      return false
    } finally {
      inFlight = false
      if (showLoading) loading.value = false
    }
  }

  function startPolling() {
    stopPolling()
    polling.value = true
    pollHandle = setInterval(() => loadSession(), 2000)
  }

  function stopPolling() {
    if (pollHandle !== null) {
      clearInterval(pollHandle)
      pollHandle = null
    }
    polling.value = false
  }

  async function doCloseSession(): Promise<boolean> {
    const sessionId = sessionIdInput.value.trim()
    if (!sessionId || !adminActionsAvailable.value) return false
    try {
      await closeSession(sessionId, adminTokenInput.value.trim() || undefined)
      clearLoadedSession()
      return true
    } catch (e: any) {
      setStatus(e.message || 'close failed', true)
      return false
    }
  }

  async function doDisconnectMember(agentName: string): Promise<boolean> {
    const sessionId = sessionIdInput.value.trim()
    if (!sessionId || !adminActionsAvailable.value) return false
    try {
      const result = await disconnectMember(sessionId, agentName, adminTokenInput.value.trim() || undefined)
      if (result.session_closed) {
        clearLoadedSession()
      } else {
        await loadSession()
      }
      return true
    } catch (e: any) {
      setStatus(e.message || 'disconnect failed', true)
      return false
    }
  }

  function resetFilters() {
    timelineFilter.value = 'all'
    agentFilter.value = ''
    problemMode.value = false
  }

  // ── Lifecycle ──

  function applyProgrammaticContext() {
    if (!programmaticContext) return
    sessionIdInput.value = programmaticContext.sessionId
    agentNameInput.value = programmaticContext.agentName || ''
    memberTokenInput.value = programmaticContext.memberToken || ''
    adminTokenInput.value = programmaticContext.adminToken || ''
  }

  async function loadFromQueryOrStorage() {
    if (programmaticContext) {
      // Host view supplies access directly: skip URL query/hash and
      // sessionStorage resolution entirely. The member token (if any) still
      // goes through the same one-time authMemberSession exchange below via
      // loadSession(), and is dropped from memory right after.
      applyProgrammaticContext()
    } else {
      const hasQueryContext = Boolean(
        route.query.session_id ||
        route.query.agent_name ||
        route.query.member_token ||
        route.query.token ||
        readMemberTokenFromHash(),
      )
      if (hasQueryContext) {
        applyQueryParams()
      } else {
        restoreAccess()
        // Resuming from storage after a reload: the member token was never
        // persisted, but the httpOnly cookie survives the reload. Treat the
        // member session as already exchanged so the poll rides the cookie with
        // no token. If the cookie is gone/expired, the first poll's 401/403
        // routes back to the access form.
        if (sessionIdInput.value.trim() && agentNameInput.value.trim() && !memberTokenInput.value.trim()) {
          memberSessionExchanged = true
        }
      }
    }
    if (sessionIdInput.value.trim()) {
      accessMode.value = inferAccessMode()
      const ok = await loadSession(true)
      if (ok) {
        accessCompact.value = true
        startPolling()
      }
    }
  }

  function handleVisibilityChange() {
    if (document.hidden) {
      stopPolling()
    } else if (sessionIdInput.value.trim()) {
      startPolling()
      loadSession()
    }
  }

  onMounted(async () => {
    await checkAuth()
    await loadFromQueryOrStorage()
    document.addEventListener('visibilitychange', handleVisibilityChange)
  })

  watch(
    () => [route.query.session_id, route.query.agent_name, route.query.member_token, route.query.token],
    () => {
      loadFromQueryOrStorage()
    },
  )

  onUnmounted(() => {
    stopPolling()
    document.removeEventListener('visibilitychange', handleVisibilityChange)
  })

  return {
    // Auth
    dashboardAuthenticated,
    dashboardTokenRequired,
    // Access
    sessionIdInput,
    agentNameInput,
    memberTokenInput,
    adminTokenInput,
    accessMode,
    accessCompact,
    adminActionsAvailable,
    // Session
    payload,
    loading,
    polling,
    statusMessage,
    statusIsError,
    isFirstRender,
    // Computed
    connectedSet,
    members,
    activityMap,
    visibleMembers,
    filteredHistory,
    trafficSnapshot,
    healthState,
    problemSummary,
    // Filters
    timelineFilter,
    agentFilter,
    problemMode,
    showRawJson,
    // Actions
    setStatus,
    loadSession,
    startPolling,
    stopPolling,
    doCloseSession,
    doDisconnectMember,
    persistAccess,
    resetFilters,
    inferAccessMode,
  }
}
