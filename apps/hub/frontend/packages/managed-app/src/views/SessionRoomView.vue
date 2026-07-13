<template>
  <div>
    <header>
      <ManagedNav />
    </header>
    <main id="main-content">
      <section class="room-page" :class="{ 'live-room-page': !!session && !isClosed }">
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

        <!-- Closed room: no live polling, but the durable archive (wall + files)
             stays readable instead of an error/retry loop. -->
        <template v-else-if="isClosed">
          <div class="closed-notice">
            <p class="empty-title">{{ t('session_room_closed_title') }}</p>
            <p class="closed-body">{{ t('session_room_closed_body') }}</p>
            <RouterLink :to="`/managed/ui/workspaces/${encodeURIComponent(slug)}`" class="primary-button">
              {{ t('session_back_to_sessions') }}
            </RouterLink>
          </div>
          <section class="archive-panel">
            <h2 class="archive-title">{{ t('room_tab_wall') }}</h2>
            <RoomWallPanel :slug="slug" :session-id="sessionId" />
          </section>
          <section class="archive-panel">
            <h2 class="archive-title">{{ t('room_tab_files') }}</h2>
            <RoomFilesPanel :slug="slug" :session-id="sessionId" />
          </section>
        </template>

        <RoomLive
          v-else
          :key="`${slug}:${sessionId}`"
          :slug="slug"
          :session-id="sessionId"
          :ws-session="session"
          @closed="markClosed"
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
import RoomWallPanel from '../components/room/RoomWallPanel.vue'
import RoomFilesPanel from '../components/room/RoomFilesPanel.vue'
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
const closedLocally = ref(false)

// Only an explicit 'closed' counts — older backends omit live_status and the
// room must still go live for them.
const isClosed = computed(() =>
  closedLocally.value || session.value?.live_status === 'closed'
)

function markClosed() {
  closedLocally.value = true
}

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
  closedLocally.value = false
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
  /* The live room uses the whole viewport: slim margins, wide cap — the
     collapsed sidebar's leftover space belongs to the cockpit. */
  max-width: 1760px;
  margin: 12px auto;
  padding: 0 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.room-page.live-room-page {
  height: calc(100dvh - 78px);
  margin-block: 0;
  padding-block: 10px;
  overflow: hidden;
  min-height: 0;
}
.room-page.live-room-page > :deep(*) { min-height: 0; }
.room-skeleton { display: flex; flex-direction: column; gap: 14px; }
.closed-notice {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 32px 24px;
  text-align: center;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--panel);
}
.closed-body { margin: 0; color: var(--muted); font-size: 0.9rem; }
.archive-panel {
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--panel);
  padding: 18px;
}
.archive-title {
  margin: 0 0 12px;
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}
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
  .room-page.live-room-page {
    height: auto;
    min-height: calc(100dvh - 72px);
    margin: 12px auto;
    padding-block: 0;
    overflow: visible;
  }
}
</style>
