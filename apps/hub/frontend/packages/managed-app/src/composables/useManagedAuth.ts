import { ref, computed, readonly } from 'vue'
import { useRouter } from 'vue-router'
import { login as apiLogin, fetchMe, logout as apiLogout, type ManagedUser } from '../api/managed'

const user = ref<ManagedUser | null>(null)
const loading = ref(false)
const checked = ref(false)

function isSafeInternalPath(value: string | undefined): value is string {
  return typeof value === 'string' && value.startsWith('/') && !value.startsWith('//')
}

export function managedHomePathFor(identity?: Pick<ManagedUser, 'deployment_mode' | 'default_workspace' | 'redirect_url' | 'role'> | null): string {
  if (isSafeInternalPath(identity?.redirect_url)) {
    return identity.redirect_url
  }
  if (identity?.deployment_mode === 'single_workspace' && identity.default_workspace?.slug) {
    return `/managed/ui/workspaces/${encodeURIComponent(identity.default_workspace.slug)}`
  }
  if (identity?.role === 'instance_admin') {
    return '/managed/admin/workspaces/ui'
  }
  return '/managed/ui/workspaces'
}

export function useManagedAuth() {
  const router = useRouter()

  const isAuthenticated = computed(() => user.value !== null)
  const isInstanceAdmin = computed(() => user.value?.role === 'instance_admin')
  const isWorkspaceAdmin = computed(() => user.value?.role === 'workspace_admin')

  async function checkSession(force = false): Promise<ManagedUser | null> {
    if (checked.value && !force) return user.value
    loading.value = true
    try {
      user.value = await fetchMe()
      checked.value = true
      return user.value
    } catch {
      user.value = null
      checked.value = true
      return null
    } finally {
      loading.value = false
    }
  }

  async function login(email: string, password: string) {
    loading.value = true
    try {
      const result = await apiLogin(email, password)
      user.value = {
        email: result.email,
        role: result.role,
        status: 'active',
        expires_at: result.expires_at,
        deployment_mode: result.deployment_mode,
        default_workspace: result.default_workspace,
        redirect_url: result.redirect_url,
      }
      checked.value = true
      return result
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    try {
      await apiLogout()
    } catch {
      // ignore
    }
    user.value = null
    checked.value = false
    router.push({ name: 'login' })
  }

  function buildLoginRedirectTarget(explicitRedirectTo?: string): string | undefined {
    const requested = String(explicitRedirectTo ?? router.currentRoute.value.fullPath ?? '').trim()
    if (!requested || requested === '/managed/login' || requested.startsWith('/managed/login?')) {
      return undefined
    }
    if (!requested.startsWith('/') || requested.startsWith('//')) {
      return undefined
    }
    return requested
  }

  async function requireAuth(redirectTo?: string): Promise<ManagedUser | null> {
    // Revalidate protected routes instead of trusting the in-memory cache.
    // Browser cookies can expire or be revoked while the SPA is still open.
    const u = await checkSession(true)
    if (!u) {
      const next = buildLoginRedirectTarget(redirectTo)
      await router.replace(next ? { name: 'login', query: { redirect: next } } : { name: 'login' })
      return null
    }
    return u
  }

  async function requireRole(role: string): Promise<ManagedUser | null> {
    const u = await requireAuth()
    if (!u) return null
    if (u.role !== role) {
      await router.replace({ name: 'dashboard' })
      return null
    }
    return u
  }

  return {
    user: readonly(user),
    loading: readonly(loading),
    checked: readonly(checked),
    isAuthenticated,
    isInstanceAdmin,
    isWorkspaceAdmin,
    checkSession,
    login,
    logout,
    requireAuth,
    requireRole,
    managedHomePathFor,
  }
}
