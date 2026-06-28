<template>
  <div>
    <header>
      <ManagedNav />
    </header>
    <main id="main-content">
      <section class="panel">
        <div class="panel-header">
          <div>
            <span class="panel-kicker">{{ t('session_detail_kicker') }}</span>
            <h1 class="panel-title">{{ sessionTitle }}</h1>
            <p class="panel-sub">{{ t('room_wall_body') }}</p>
            <div v-if="session" class="header-meta">
              <span class="pill">{{ t('session_owner') }}: <strong>{{ session.owner_agent_name }}</strong></span>
              <span v-if="session.project" class="pill">{{ t('label_project') }}: <strong>{{ session.project }}</strong></span>
              <span class="pill"><code>{{ session.session_id }}</code></span>
            </div>
          </div>
          <div class="header-actions">
            <RouterLink :to="`/managed/ui/workspaces/${encodeURIComponent(slug)}`" class="back-link">
              &larr; {{ t('session_back_to_sessions') }}
            </RouterLink>
            <RouterLink v-if="session" :to="livePath" class="primary-link">
              {{ t('session_open_live') }} &rarr;
            </RouterLink>
          </div>
        </div>

        <div v-if="loading" class="surface-card" role="status" :aria-label="t('loading')">
          <SkeletonBlock h="14px" width="30%" />
          <SkeletonBlock h="22px" width="65%" />
          <SkeletonBlock h="80px" width="100%" />
        </div>

        <div v-else class="detail-grid">
          <article class="surface-card">
            <div class="section-head">
              <span class="section-chip">{{ t('room_wall_section') }}</span>
              <h2>{{ t('room_wall_title') }}</h2>
              <p>{{ t('room_wall_help') }}</p>
            </div>

            <form class="wall-form" @submit.prevent="handleCreatePost">
              <label class="sr-only" for="wall-body">{{ t('room_wall_new_post') }}</label>
              <textarea
                id="wall-body"
                v-model="newPostBody"
                rows="4"
                :placeholder="t('room_wall_placeholder')"
                :disabled="posting"
              ></textarea>
              <label class="checkbox-row">
                <input v-model="newPostPinned" type="checkbox" :disabled="posting" />
                <span>{{ t('room_wall_pin_post') }}</span>
              </label>
              <button class="primary-button" type="submit" :disabled="posting || !newPostBody.trim()">
                <span v-if="posting" class="spinner" aria-hidden="true"></span>
                {{ t('room_wall_post') }}
              </button>
            </form>
          </article>

          <article class="surface-card">
            <div class="section-head">
              <span class="section-chip section-chip-accent">{{ t('room_wall_posts') }}</span>
              <h2>{{ t('room_wall_current') }}</h2>
            </div>

            <div v-if="posts.length === 0" class="empty-state compact">
              <p class="empty-title">{{ t('room_wall_empty') }}</p>
              <p class="empty-body">{{ t('room_wall_empty_body') }}</p>
            </div>

            <div v-else class="wall-posts">
              <article v-for="post in posts" :key="post.post_id" class="wall-post" :class="{ pinned: post.pinned }">
                <div class="wall-post-meta">
                  <span v-if="post.pinned" class="pin-badge">{{ t('room_wall_pinned') }}</span>
                  <span>{{ post.author_name }}</span>
                  <span class="muted">{{ post.author_type }}</span>
                  <time :datetime="post.created_at">{{ relativeTime(post.created_at) }}</time>
                </div>
                <p class="wall-post-body">{{ post.body }}</p>
                <div class="wall-post-actions">
                  <button class="secondary-button" type="button" @click="togglePinned(post)" :disabled="mutatingPostId === post.post_id">
                    {{ post.pinned ? t('room_wall_unpin') : t('room_wall_pin') }}
                  </button>
                  <button class="danger" type="button" @click="deletePost(post)" :disabled="mutatingPostId === post.post_id">
                    {{ t('confirm_delete_btn') }}
                  </button>
                </div>
              </article>
            </div>
          </article>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import ManagedNav from '../components/ManagedNav.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import {
  createSessionWallPost,
  deleteSessionWallPost,
  fetchSessionDetail,
  fetchSessionWall,
  updateSessionWallPost,
  type RoomWallPost,
  type WorkspaceSession,
} from '../api/managed'
import { getApiErrorMessage } from '../api/client'
import { useManagedAuth } from '../composables/useManagedAuth'
import { useManagedI18n } from '../i18n'
import { useToast } from '../composables/useToast'
import { buildManagedSessionDashboardPath } from '../lib/sessionLive'
import { relativeTime } from '../lib/time'

const route = useRoute()
const { requireAuth } = useManagedAuth()
const { t } = useManagedI18n()
const toast = useToast()

const slug = computed(() => String(route.params.slug || ''))
const sessionId = computed(() => String(route.params.sessionId || ''))

const loading = ref(true)
const posting = ref(false)
const mutatingPostId = ref('')
const session = ref<WorkspaceSession | null>(null)
const posts = ref<RoomWallPost[]>([])
const newPostBody = ref('')
const newPostPinned = ref(false)

const sessionTitle = computed(() => session.value?.title || t('session_detail_title'))
const livePath = computed(() => {
  if (!session.value) return '/managed/dashboard'
  return buildManagedSessionDashboardPath({
    sessionId: session.value.session_id,
    agentName: session.value.owner_agent_name,
    memberToken: session.value.owner_member_token,
  })
})

async function loadDetail() {
  const [detail, wall] = await Promise.all([
    fetchSessionDetail(slug.value, sessionId.value),
    fetchSessionWall(slug.value, sessionId.value),
  ])
  session.value = detail.workspace_session
  posts.value = wall.posts
}

async function handleCreatePost() {
  const body = newPostBody.value.trim()
  if (!body) return
  posting.value = true
  try {
    const result = await createSessionWallPost(slug.value, sessionId.value, {
      body,
      pinned: newPostPinned.value,
    })
    posts.value = result.post.pinned ? [result.post, ...posts.value] : [...posts.value, result.post]
    newPostBody.value = ''
    newPostPinned.value = false
    toast.show(t('room_wall_posted'), 'success')
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
  } finally {
    posting.value = false
  }
}

async function togglePinned(post: RoomWallPost) {
  mutatingPostId.value = post.post_id
  try {
    const result = await updateSessionWallPost(slug.value, sessionId.value, post.post_id, {
      pinned: !post.pinned,
    })
    posts.value = posts.value
      .map(item => item.post_id === post.post_id ? result.post : item)
      .sort((a, b) => Number(b.pinned) - Number(a.pinned) || new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
  } finally {
    mutatingPostId.value = ''
  }
}

async function deletePost(post: RoomWallPost) {
  mutatingPostId.value = post.post_id
  try {
    await deleteSessionWallPost(slug.value, sessionId.value, post.post_id)
    posts.value = posts.value.filter(item => item.post_id !== post.post_id)
    toast.show(t('room_wall_deleted'), 'success')
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
  } finally {
    mutatingPostId.value = ''
  }
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
</script>

<style scoped>
.panel {
  max-width: 1040px;
  margin: 32px auto;
  padding: 28px;
}
.panel-header,
.header-actions,
.detail-grid,
.wall-posts,
.wall-form {
  display: flex;
  gap: 18px;
}
.panel-header {
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
  flex-wrap: wrap;
}
.header-actions,
.detail-grid,
.wall-posts,
.wall-form {
  flex-direction: column;
}
.panel-kicker,
.section-chip {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--accent);
  font-weight: 700;
}
.panel-title {
  margin: 6px 0 8px;
  color: var(--text-1);
  font-size: 1.6rem;
}
.panel-sub,
.section-head p,
.muted {
  color: var(--text-2);
}
.header-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}
.surface-card {
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xl);
  background: var(--glass-bg);
  padding: 24px;
}
.back-link,
.primary-link {
  text-decoration: none;
}
.primary-link {
  color: var(--accent);
  font-weight: 700;
}
.back-link {
  color: var(--text-2);
}
textarea {
  width: 100%;
  resize: vertical;
}
.checkbox-row {
  display: flex;
  gap: 10px;
  align-items: center;
  color: var(--text-2);
}
.wall-post {
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  padding: 16px;
  background: var(--surface-1);
}
.wall-post.pinned {
  border-color: var(--accent-glow);
  background: var(--accent-subtle);
}
.wall-post-meta,
.wall-post-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
}
.wall-post-meta {
  font-size: 0.82rem;
  color: var(--text-2);
}
.wall-post-body {
  color: var(--text-1);
  white-space: pre-wrap;
  line-height: 1.55;
}
.pin-badge {
  border: 1px solid var(--accent-glow);
  border-radius: 999px;
  color: var(--accent);
  padding: 3px 8px;
  font-size: 0.72rem;
  font-weight: 700;
}
@media (max-width: 720px) {
  .panel {
    padding: 18px;
  }
}
</style>
