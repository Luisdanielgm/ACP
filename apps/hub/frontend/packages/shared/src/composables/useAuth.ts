import { ref } from 'vue'

export function useAuth(endpoint = '/dashboard/auth/session') {
  const authenticated = ref(false)
  const tokenRequired = ref(false)
  const loading = ref(false)

  async function checkSession() {
    loading.value = true
    try {
      const res = await fetch(endpoint, { credentials: 'include' })
      if (!res.ok) {
        authenticated.value = false
        return
      }
      const data = await res.json()
      authenticated.value = data.authenticated === true
      tokenRequired.value = data.token_required === true
    } catch {
      authenticated.value = false
    } finally {
      loading.value = false
    }
  }

  return { authenticated, tokenRequired, loading, checkSession }
}
