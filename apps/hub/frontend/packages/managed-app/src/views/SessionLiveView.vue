<template>
  <div v-if="resolving" class="live-resolve">
    <div class="live-resolve-card">
      <div class="live-resolve-kicker">ACP Managed</div>
      <h1 class="live-resolve-title">{{ t('loading') }}</h1>
      <p class="live-resolve-copy">
        {{ resolveMessage }}
        <span class="loading-dots" aria-hidden="true"><span></span><span></span><span></span></span>
      </p>
    </div>
  </div>
  <SessionDashboardView
    v-else
    auth-endpoint="/managed/dashboard/auth/session"
    redirect-path="/managed/dashboard"
  />
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { SessionDashboardView } from '@acp/public-app'
import { fetchSessionDetail } from '../api/managed'
import { useManagedAuth } from '../composables/useManagedAuth'
import { useManagedI18n } from '../i18n'
import { buildManagedSessionDashboardPath } from '../lib/sessionLive'

const route = useRoute()
const router = useRouter()
const { requireAuth } = useManagedAuth()
const { t } = useManagedI18n()

const resolving = ref(false)

const routeSessionId = computed(() => String(route.params.sessionId || ''))
const routeSlug = computed(() => String(route.params.slug || ''))
const hasQueryContext = computed(() => Boolean(String(route.query.session_id || '').trim()))
const resolveMessage = computed(() =>
  hasQueryContext.value
    ? t('loading')
    : t('session_resolve_loading')
)

onMounted(async () => {
  if (hasQueryContext.value || !routeSessionId.value || !routeSlug.value) {
    return
  }

  resolving.value = true
  try {
    const currentUser = await requireAuth()
    if (!currentUser) return

    const data = await fetchSessionDetail(routeSlug.value, routeSessionId.value)
    await router.replace(
      buildManagedSessionDashboardPath({
        sessionId: data.workspace_session.session_id,
        agentName: data.workspace_session.owner_agent_name,
        memberToken: data.workspace_session.owner_member_token,
      })
    )
  } catch {
    await router.replace(
      buildManagedSessionDashboardPath({
        sessionId: routeSessionId.value,
      })
    )
  } finally {
    resolving.value = false
  }
})
</script>

<style scoped>
.live-resolve {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  position: relative;
  overflow: hidden;
}
.live-resolve::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 600px;
  height: 600px;
  background: radial-gradient(circle, var(--accent-subtle) 0%, transparent 70%);
  pointer-events: none;
  animation: hero-glow 5s ease-in-out infinite;
}
@keyframes hero-glow {
  0%, 100% { opacity: 0.5; transform: translate(-50%, -50%) scale(1); }
  50% { opacity: 0.85; transform: translate(-50%, -50%) scale(1.1); }
}

.live-resolve-card {
  width: min(500px, 100%);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xl);
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  padding: 32px;
  box-shadow: var(--shadow-lg), 0 0 60px var(--accent-subtle);
  animation: card-enter var(--transition-spring);
  position: relative;
  z-index: 1;
}
@keyframes card-enter {
  from { opacity: 0; transform: scale(0.95) translateY(12px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}
.live-resolve-card:hover {
  border-color: var(--accent-glow);
  box-shadow: var(--shadow-lg), 0 0 80px var(--accent-glow);
}

.live-resolve-kicker {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: 8px;
}

.live-resolve-title {
  margin: 12px 0 10px;
  font-size: 1.5rem;
  color: var(--text-1);
  letter-spacing: -0.02em;
  font-weight: 800;
}

.live-resolve-copy {
  margin: 0;
  color: var(--text-2);
  line-height: 1.6;
  font-size: 0.92rem;
}

.loading-dots {
  display: inline-flex;
  gap: 4px;
  margin-left: 8px;
  vertical-align: middle;
}
.loading-dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  animation: dot-pulse 1.4s ease-in-out infinite;
}
.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes dot-pulse {
  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1); }
}

@media (max-width: 540px) {
  .live-resolve-card {
    padding: 24px;
  }
}
</style>