<template>
  <div>
    <header>
      <ManagedNav />
    </header>
    <main id="main-content">
      <section class="room-page">
        <div v-if="session" class="room-toolbar">
          <div class="toolbar-meta">
            <span class="pill">{{ session.owner_agent_name }}</span>
            <span v-if="session.project" class="pill">{{ session.project }}</span>
            <span class="pill mono">{{ session.session_id }}</span>
          </div>
        </div>

        <div v-if="loading" class="room-skeleton" role="status" :aria-label="t('loading')">
          <SkeletonBlock h="52px" width="100%" />
          <SkeletonBlock h="320px" width="100%" />
          <SkeletonBlock h="44px" width="60%" />
        </div>

        <div v-else-if="!session" class="empty-state">
          <p class="empty-title">{{ t('session_room_missing') }}</p>
          <RouterLink :to="`/managed/ui/workspaces/${encodeURIComponent(slug)}`" class="primary-button">
            {{ t('session_back_to_sessions') }}
          </RouterLink>
        </div>

        <RoomLive
          v-else
          :key="`${slug}:${sessionId}`"
          :slug="slug"
          :session-id="sessionId"
          :ws-session="session"
        />
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch, watchEffect } from 'vue'
import { useRoute } from 'vue-router'
import ManagedNav from '../components/ManagedNav.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import RoomLive from '../components/room/RoomLive.vue'
import { fetchSessionDetail, type WorkspaceSession } from '../api/managed'
import { getApiErrorMessage } from '../api/client'
import { useManagedAuth } from '../composables/useManagedAuth'
import { useManagedI18n } from '../i18n'
import { useToast } from '../composables/useToast'

const route = useRoute()
const { requireAuth } = useManagedAuth()
const { t } = useManagedI18n()
const toast = useToast()

const slug = computed(() => String(route.params.slug || ''))
const sessionId = computed(() => String(route.params.sessionId || ''))

const loading = ref(true)
const session = ref<WorkspaceSession | null>(null)

async function loadDetail() {
  const detail = await fetchSessionDetail(slug.value, sessionId.value)
  session.value = detail.workspace_session
}

onMounted(async () => {
  const currentUser = await requireAuth()
  if (!currentUser) return
  try {
    await loadDetail()
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
  } finally {
    loading.value = false
  }
})

watch([slug, sessionId], async () => {
  loading.value = true
  session.value = null
  try {
    await loadDetail()
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
  } finally {
    loading.value = false
  }
})

watchEffect(() => {
  document.title = session.value?.title || t('session_detail_title')
})
</script>

<style scoped>
.room-page {
  max-width: 1400px;
  margin: 24px auto;
  padding: 0 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.room-toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}
.toolbar-meta { display: inline-flex; gap: 8px; flex-wrap: wrap; }
.pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--soft);
  color: var(--muted);
  font-size: 0.74rem;
  font-weight: 600;
}
.pill.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.7rem; }
.room-skeleton { display: flex; flex-direction: column; gap: 14px; }
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 60px 24px;
  text-align: center;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--panel);
}
.empty-title { margin: 0; color: var(--muted); }
@media (max-width: 768px) {
  .room-page { padding: 0 14px; margin: 16px auto; }
}
</style>
