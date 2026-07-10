<template>
  <div class="room-panel-body">
    <form class="wall-form" @submit.prevent="handleCreatePost">
      <label class="sr-only" for="room-wall-body">{{ t('room_wall_new_post') }}</label>
      <textarea
        id="room-wall-body"
        v-model="newPostBody"
        rows="3"
        :placeholder="t('room_wall_placeholder')"
        :disabled="posting"
      ></textarea>
      <div class="wall-form-actions">
        <label class="checkbox-row">
          <input v-model="newPostPinned" type="checkbox" :disabled="posting" />
          <span>{{ t('room_wall_pin_post') }}</span>
        </label>
        <button class="primary-button" type="submit" :disabled="posting || !newPostBody.trim()">
          <span v-if="posting" class="spinner" aria-hidden="true"></span>
          {{ t('room_wall_post') }}
        </button>
      </div>
    </form>

    <div v-if="loading" class="panel-note">{{ t('loading') }}</div>

    <div v-else-if="posts.length === 0" class="empty-note">
      <p class="empty-title">{{ t('room_wall_empty') }}</p>
      <p class="empty-body">{{ t('room_wall_empty_body') }}</p>
    </div>

    <div v-else class="wall-posts">
      <article v-for="post in posts" :key="post.post_id" class="wall-post" :class="{ pinned: post.pinned }">
        <div class="wall-post-meta">
          <span v-if="post.pinned" class="pin-badge"><RoomIcon name="pin" :size="11" /> {{ t('room_wall_pinned') }}</span>
          <span class="wall-author">{{ post.author_name }}</span>
          <span class="muted">{{ post.author_type }}</span>
          <time :datetime="post.created_at">{{ relativeTime(post.created_at) }}</time>
          <span class="wall-post-actions">
            <button
              class="icon-button"
              type="button"
              :aria-label="post.pinned ? t('room_wall_unpin') : t('room_wall_pin')"
              :title="post.pinned ? t('room_wall_unpin') : t('room_wall_pin')"
              :disabled="mutatingPostId === post.post_id"
              @click="togglePinned(post)"
            >
              <RoomIcon :name="post.pinned ? 'x' : 'pin'" :size="14" />
            </button>
            <button
              class="icon-button danger"
              type="button"
              :aria-label="t('confirm_delete_btn')"
              :title="t('confirm_delete_btn')"
              :disabled="mutatingPostId === post.post_id"
              @click="deletePost(post)"
            >
              <RoomIcon name="trash" :size="14" />
            </button>
          </span>
        </div>
        <p class="wall-post-body">{{ post.body }}</p>
      </article>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import {
  createSessionWallPost,
  deleteSessionWallPost,
  fetchSessionWall,
  updateSessionWallPost,
  type RoomWallPost,
} from '../../api/managed'
import { getApiErrorMessage } from '../../api/client'
import { useManagedI18n } from '../../i18n'
import { useToast } from '../../composables/useToast'
import { relativeTime } from '../../lib/time'
import RoomIcon from './RoomIcon.vue'

const props = defineProps<{
  slug: string
  sessionId: string
}>()

const emit = defineEmits<{
  count: [value: number]
  pinned: [post: RoomWallPost | null]
}>()

const { t } = useManagedI18n()
const toast = useToast()

const loading = ref(true)
const posting = ref(false)
const mutatingPostId = ref('')
const posts = ref<RoomWallPost[]>([])
const newPostBody = ref('')
const newPostPinned = ref(false)

watch(posts, value => {
  emit('count', value.length)
  const pinned = value.filter(post => post.pinned)
  emit('pinned', pinned.length ? pinned[pinned.length - 1] : null)
}, { deep: false })

async function loadWall() {
  loading.value = true
  try {
    const wall = await fetchSessionWall(props.slug, props.sessionId)
    posts.value = wall.posts
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
  } finally {
    loading.value = false
  }
}

async function handleCreatePost() {
  const body = newPostBody.value.trim()
  if (!body) return
  posting.value = true
  try {
    const result = await createSessionWallPost(props.slug, props.sessionId, {
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
    const result = await updateSessionWallPost(props.slug, props.sessionId, post.post_id, {
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
    await deleteSessionWallPost(props.slug, props.sessionId, post.post_id)
    posts.value = posts.value.filter(item => item.post_id !== post.post_id)
    toast.show(t('room_wall_deleted'), 'success')
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
  } finally {
    mutatingPostId.value = ''
  }
}

onMounted(loadWall)
</script>

<style scoped>
.room-panel-body { display: flex; flex-direction: column; gap: 16px; }
.wall-form { display: flex; flex-direction: column; gap: 10px; }
.wall-form-actions { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
textarea {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--soft);
  color: var(--ink);
  font-size: 0.9rem;
  resize: vertical;
}
textarea:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); outline: none; }
.checkbox-row { display: flex; gap: 8px; align-items: center; color: var(--muted); font-size: 0.85rem; }
.panel-note { color: var(--muted); font-size: 0.9rem; }
.empty-note { text-align: center; padding: 18px 12px; }
.empty-title { margin: 0 0 4px; color: var(--ink); font-weight: 600; }
.empty-body { margin: 0; color: var(--muted); font-size: 0.88rem; }
.wall-posts { display: flex; flex-direction: column; gap: 10px; }
.wall-post { border: 1px solid var(--line); border-radius: 14px; padding: 12px 14px; background: var(--card-bg); }
.wall-post.pinned { border-color: var(--accent-glow); background: var(--accent-soft); }
.wall-post-meta { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; font-size: 0.8rem; color: var(--muted); }
.wall-author { color: var(--ink); font-weight: 600; }
.wall-post-actions { margin-left: auto; display: inline-flex; gap: 6px; }
.wall-post-body { margin: 8px 0 0; color: var(--ink); white-space: pre-wrap; line-height: 1.5; font-size: 0.92rem; }
.pin-badge { display: inline-flex; align-items: center; gap: 4px; border: 1px solid var(--accent-glow); border-radius: 999px; color: var(--accent); padding: 2px 8px; font-size: 0.7rem; font-weight: 700; }
.muted { color: var(--muted); }
.icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  transition: all 0.15s ease;
}
.icon-button:hover { color: var(--ink); border-color: var(--hover-line); }
.icon-button.danger:hover { color: #F0997B; border-color: rgba(240, 153, 123, 0.4); }
.icon-button:disabled { opacity: 0.5; cursor: default; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
</style>
