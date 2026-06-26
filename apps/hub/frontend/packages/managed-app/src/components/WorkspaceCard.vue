<template>
  <article
    ref="rootRef"
    class="workspace-admin-card"
    :class="{ 'secondary-card': variant === 'secondary' }"
    role="region"
    :aria-label="workspace.name"
  >
    <div class="workspace-card-head">
      <div class="workspace-card-summary">
        <div class="workspace-card-title">{{ workspace.name }}</div>
        <div class="workspace-card-meta">
          <span class="pill">{{ t('ws_slug') }}: <strong>{{ workspace.slug }}</strong></span>
          <span class="pill" :class="'pill-status-' + workspace.status">
            <span class="pill-icon" aria-hidden="true">{{ statusGlyph }}</span>
            {{ t('status_' + workspace.status) }}
          </span>
          <span class="pill">
            {{ t('ws_admin') }}:
            <strong>{{ workspaceAdmin?.email ?? t('ws_admin_pending') }}</strong>
          </span>
          <span v-if="hasPendingInvitation" class="pill pill-pending" role="status">
            <span class="pill-icon" aria-hidden="true">&hellip;</span>
            {{ t('admin_pending_invitation') }}
          </span>
        </div>
      </div>

      <div class="workspace-card-actions-head">
        <template v-if="variant === 'secondary'">
          <span class="workspace-note">{{ t('dash_other_workspace_note') }}</span>
        </template>
        <RouterLink v-else :to="openPath" class="secondary-button">
          {{ t('admin_open_workspace') }}
        </RouterLink>
        <button
          type="button"
          class="actions-trigger"
          :aria-label="t('manage_workspace')"
          :aria-expanded="menuOpen"
          aria-haspopup="true"
          @click.stop="toggleMenu"
        >
          <span aria-hidden="true">&#x22EF;</span>
        </button>
      </div>
    </div>

    <transition name="actions">
      <section
        v-if="menuOpen"
        class="actions-panel"
        role="group"
        :aria-label="t('manage_workspace')"
        @click.stop
      >
        <header class="actions-header">
          <span class="actions-kicker">{{ t('manage_workspace') }}</span>
          <button
            type="button"
            class="actions-close"
            :aria-label="t('dismiss')"
            @click="menuOpen = false"
          >
            &times;
          </button>
        </header>

        <article v-if="!workspaceAdmin" class="action-block">
          <div class="action-head">
            <h4>{{ t('admin_invite_email') }}</h4>
            <p>{{ t('action_invite_help') }}</p>
          </div>
          <form class="action-form" @submit.prevent="submitInvite">
            <label :for="inviteId" class="sr-only">{{ t('admin_invite_email') }}</label>
            <input
              :id="inviteId"
              v-model="inviteEmail"
              type="email"
              :placeholder="t('admin_invite_email_ph')"
              required
            />
            <button type="submit">{{ t('admin_invite_submit') }}</button>
          </form>
        </article>

        <article v-else class="action-block action-block-info">
          <p class="action-info">{{ t('action_admin_already_assigned', { email: workspaceAdmin.email }) }}</p>
        </article>

        <article class="action-block">
          <div class="action-head">
            <h4>{{ t('action_rename_title') }}</h4>
            <p>{{ t('action_rename_help') }}</p>
          </div>
          <form class="action-form" @submit.prevent="submitRename">
            <label :for="renameId" class="sr-only">{{ t('admin_rename_placeholder') }}</label>
            <input
              :id="renameId"
              v-model="renameName"
              type="text"
              :placeholder="workspace.name"
            />
            <button type="submit" :disabled="!renameName.trim() || renameName.trim() === workspace.name">
              {{ t('action_rename_submit') }}
            </button>
          </form>
        </article>

        <article class="action-block">
          <div class="action-head">
            <h4>{{ t('action_status_title') }}</h4>
            <p>{{ t('action_status_help') }}</p>
          </div>
          <form class="action-form" @submit.prevent="submitStatusChange">
            <label :for="statusId" class="sr-only">{{ t('action_status_title') }}</label>
            <select :id="statusId" v-model="statusChange">
              <option value="active">{{ t('status_active') }}</option>
              <option value="disabled">{{ t('status_disabled') }}</option>
            </select>
            <button type="submit" :disabled="statusChange === workspace.status">
              {{ t('action_status_submit') }}
            </button>
          </form>
        </article>

        <article class="action-block action-block-danger">
          <div class="action-head">
            <h4>{{ t('action_delete_title') }}</h4>
            <p>{{ t('action_delete_help') }}</p>
          </div>
          <button
            class="danger"
            type="button"
            @click="emit('delete', workspace.slug)"
            :aria-label="t('admin_delete_submit') + ' ' + workspace.name"
          >
            {{ t('admin_delete_submit') }}
          </button>
        </article>
      </section>
    </transition>

    <div v-if="invitationUrl" class="invite-result" role="alert">
      <p class="invite-result-label">{{ t('invitation_created_title') }}</p>
      <code>{{ invitationUrl }}</code>
      <button
        class="secondary-button copy-btn"
        type="button"
        @click="copyInviteUrl"
        :aria-label="t('ws_token_copy')"
      >
        {{ t('ws_token_copy') }}
      </button>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { useManagedI18n } from '../i18n'
import type { Workspace, WorkspaceMembership } from '../api/managed'

const props = withDefaults(
  defineProps<{
    workspace: Workspace
    workspaceAdmin: WorkspaceMembership | null
    hasPendingInvitation: boolean
    invitationUrl: string | null
    variant?: 'primary' | 'secondary'
  }>(),
  {
    variant: 'primary',
  },
)

const emit = defineEmits<{
  invite: [slug: string, email: string]
  update: [slug: string, data: { name?: string; status?: string }]
  delete: [slug: string]
  copy: [text: string]
}>()

const { t } = useManagedI18n()

const rootRef = ref<HTMLElement | null>(null)
const menuOpen = ref(false)
const inviteEmail = ref('')
const renameName = ref('')
const statusChange = ref<string>(props.workspace.status)

watch(
  () => props.workspace.status,
  value => {
    if (!menuOpen.value) {
      statusChange.value = value
    }
  },
)

const cardKey = props.workspace.workspace_id || props.workspace.slug
const inviteId = `ws-invite-${cardKey}`
const renameId = `ws-rename-${cardKey}`
const statusId = `ws-status-${cardKey}`

const openPath = computed(() =>
  `/managed/ui/workspaces/${encodeURIComponent(props.workspace.slug)}`,
)

const statusGlyph = computed(() => {
  switch (props.workspace.status) {
    case 'active':
      return '✓'
    case 'disabled':
      return '✕'
    default:
      return '…'
  }
})

function toggleMenu() {
  menuOpen.value = !menuOpen.value
  if (menuOpen.value) {
    // Reset transient fields to a clean state every time the panel opens so
    // users do not see stale typing from a previous interaction.
    inviteEmail.value = ''
    renameName.value = ''
    statusChange.value = props.workspace.status
  }
}

function submitInvite() {
  const email = inviteEmail.value.trim()
  if (!email) return
  emit('invite', props.workspace.slug, email)
  inviteEmail.value = ''
}

function submitRename() {
  const name = renameName.value.trim()
  if (!name || name === props.workspace.name) return
  emit('update', props.workspace.slug, { name })
  renameName.value = ''
}

function submitStatusChange() {
  if (!statusChange.value || statusChange.value === props.workspace.status) return
  emit('update', props.workspace.slug, { status: statusChange.value })
}

async function copyInviteUrl() {
  const url = props.invitationUrl
  if (!url) return
  emit('copy', url)
  try {
    await navigator.clipboard.writeText(url)
  } catch {
    // The parent receives the copy event and can fall back to a manual prompt.
  }
}

function onDocumentClick(event: MouseEvent) {
  if (!menuOpen.value) return
  const root = rootRef.value
  if (!root) return
  if (!root.contains(event.target as Node)) {
    menuOpen.value = false
  }
}

function onKeydown(event: KeyboardEvent) {
  if (menuOpen.value && event.key === 'Escape') {
    menuOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
.workspace-card-head {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
}
.workspace-card-summary {
  min-width: 0;
  flex: 1;
}
.workspace-card-actions-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.actions-trigger {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-2);
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 1.1rem;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: color var(--transition-fast), background var(--transition-fast),
    border-color var(--transition-fast);
}
.actions-trigger:hover,
.actions-trigger:focus-visible {
  color: var(--text-1);
  background: var(--surface-1);
  border-color: var(--text-3, var(--text-2));
  outline: none;
}
.actions-trigger[aria-expanded='true'] {
  background: var(--surface-2);
  color: var(--text-1);
  border-color: var(--accent);
}

.actions-panel {
  margin-top: 14px;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-1);
  display: grid;
  gap: 14px;
}
.actions-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.actions-kicker {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-2);
}
.actions-close {
  background: transparent;
  border: none;
  color: var(--text-2);
  cursor: pointer;
  font-size: 1.2rem;
  line-height: 1;
  padding: 2px 6px;
  border-radius: var(--radius-sm, 4px);
}
.actions-close:hover {
  color: var(--text-1);
  background: var(--surface-2);
}
.action-block {
  display: grid;
  gap: 8px;
}
.action-block + .action-block {
  padding-top: 12px;
  border-top: 1px dashed var(--border);
}
.action-block-info {
  background: var(--surface-2);
  padding: 10px 12px;
  border-radius: var(--radius-md);
}
.action-info {
  margin: 0;
  font-size: 0.85rem;
  color: var(--text-1);
}
.action-head h4 {
  margin: 0;
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--text-1);
}
.action-head p {
  margin: 2px 0 0;
  font-size: 0.8rem;
  color: var(--text-2);
  line-height: 1.45;
}
.action-form {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.action-form input,
.action-form select {
  flex: 1 1 220px;
  min-width: 0;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-2);
  color: var(--text-1);
  font-size: 0.86rem;
}
.action-form input:focus-visible,
.action-form select:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
}
.action-form button {
  padding: 8px 14px;
  border: none;
  border-radius: var(--radius-md);
  background: var(--accent);
  color: var(--button-accent-text, white);
  font-size: 0.84rem;
  font-weight: 600;
  cursor: pointer;
  transition: opacity var(--transition-fast);
}
.action-form button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.action-block-danger .danger {
  justify-self: start;
}

.invite-result {
  margin-top: 12px;
  display: grid;
  gap: 6px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: var(--accent-subtle, var(--surface-1));
  border: 1px solid var(--accent, var(--border));
}
.invite-result-label {
  margin: 0;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-2);
}
.invite-result code {
  font-size: 0.8rem;
  word-break: break-all;
}

.actions-enter-active,
.actions-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.actions-enter-from,
.actions-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
