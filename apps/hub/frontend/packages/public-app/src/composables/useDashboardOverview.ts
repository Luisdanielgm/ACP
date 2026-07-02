import { ref, computed, onMounted, onUnmounted } from 'vue'
import { fetchAuthSession, loginDashboard, logoutDashboard } from '../api/auth'
import { fetchOverview, type OverviewPayload, type SessionData, type TraceEvent } from '../api/overview'
import { memberIssues, recentTraceSnapshot } from './dashboardHelpers'

export function useDashboardOverview(authEndpoint = '/dashboard/auth/session') {
  const authenticated = ref(false)
  const tokenRequired = ref(false)
  const locked = ref(true)
  const statusMessage = ref('')
  const statusIsError = ref(false)
  const loading = ref(false)
  const polling = ref(false)

  const payload = ref<OverviewPayload | null>(null)
  const traceEvents = ref<TraceEvent[]>([])

  const filterText = ref('')
  const issueMode = ref(false)

  let pollHandle: ReturnType<typeof setInterval> | null = null
  let inFlight = false
  let loadRequestId = 0

  const connectedSet = computed(() => new Set(payload.value?.connected_agents ?? []))

  const sessions = computed(() => payload.value?.overview?.sessions ?? [])

  const filteredSessions = computed(() => {
    let items = sessions.value.slice()
    if (filterText.value) {
      const needle = filterText.value.toLowerCase()
      items = items.filter(s => {
        if ((s.session_id || '').toLowerCase().includes(needle)) return true
        if ((s.title || '').toLowerCase().includes(needle)) return true
        if ((s.project || '').toLowerCase().includes(needle)) return true
        if ((s.created_by || '').toLowerCase().includes(needle)) return true
        return (s.members || []).some(m => (m.agent_name || '').toLowerCase().includes(needle))
      })
    }
    if (issueMode.value) {
      items = items.filter(s => sessionHasIssues(s))
    }
    return items
  })

  const trafficSnapshot = computed(() => recentTraceSnapshot(traceEvents.value))

  const issueCount = computed(() =>
    filteredSessions.value.filter(s => sessionHasIssues(s)).length
  )

  function sessionHasIssues(session: SessionData): boolean {
    return (session.members || []).some(m => memberIssues(m, connectedSet.value).length > 0)
  }

  function setStatus(msg: string, isError = false) {
    statusMessage.value = msg
    statusIsError.value = isError
  }

  async function checkAuth() {
    try {
      const session = await fetchAuthSession(authEndpoint)
      authenticated.value = session.authenticated
      tokenRequired.value = session.token_required
      return session
    } catch (e: any) {
      if (e?.status === 401) {
        tokenRequired.value = false
        authenticated.value = false
      } else {
        setStatus(e?.message || 'auth check failed', true)
      }
      return { authenticated: authenticated.value, token_required: tokenRequired.value }
    }
  }

  async function login(token: string) {
    loading.value = true
    try {
      await loginDashboard(token)
      authenticated.value = true
      locked.value = false
      await loadOverview()
      startPolling()
    } catch (e: any) {
      setStatus(e.message || 'login failed', true)
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    try {
      await logoutDashboard()
    } catch { /* ignore */ }
    authenticated.value = false
    if (tokenRequired.value) {
      locked.value = true
    }
  }

  async function loadOverview() {
    if (inFlight) return
    if (tokenRequired.value && !authenticated.value) {
      locked.value = true
      return
    }
    inFlight = true
    locked.value = false
    const requestId = ++loadRequestId
    try {
      const data = await fetchOverview()
      if (requestId !== loadRequestId) return
      payload.value = data
      traceEvents.value = data.traces || []
    } catch (e: any) {
      if (requestId !== loadRequestId) return
      setStatus(e.message || 'request failed', true)
    } finally {
      inFlight = false
    }
  }

  function startPolling() {
    stopPolling()
    polling.value = true
    pollHandle = setInterval(loadOverview, 3000)
  }

  function stopPolling() {
    if (pollHandle !== null) {
      clearInterval(pollHandle)
      pollHandle = null
    }
    polling.value = false
  }

  function clearTraces() {
    traceEvents.value = []
  }

  function resetFilters() {
    filterText.value = ''
    issueMode.value = false
  }

  function handleVisibilityChange() {
    if (document.hidden) {
      stopPolling()
    } else if (!locked.value) {
      startPolling()
      loadOverview()
    }
  }

  onMounted(async () => {
    // Register unconditionally so tab pause/resume works after in-app login;
    // the handler itself is a no-op while locked.
    document.addEventListener('visibilitychange', handleVisibilityChange)
    const session = await checkAuth()
    if (tokenRequired.value && !session.authenticated) {
      locked.value = true
      return
    }
    locked.value = false
    await loadOverview()
    startPolling()
  })

  onUnmounted(() => {
    stopPolling()
    document.removeEventListener('visibilitychange', handleVisibilityChange)
  })

  return {
    authenticated,
    tokenRequired,
    locked,
    loading,
    polling,
    statusMessage,
    statusIsError,
    payload,
    traceEvents,
    filterText,
    issueMode,
    connectedSet,
    sessions,
    filteredSessions,
    trafficSnapshot,
    issueCount,
    login,
    logout,
    loadOverview,
    startPolling,
    clearTraces,
    resetFilters,
    setStatus,
  }
}
