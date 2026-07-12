<template>
  <div class="room-panel-body">
    <form class="operator-form" @submit.prevent="handleSendOperatorMessage">
      <div class="operator-row">
        <label class="operator-label" for="room-operator-to">{{ t('web_operator_to') }}</label>
        <select id="room-operator-to" v-model="operatorTo" :disabled="operatorSending">
          <option value="all">{{ t('web_operator_all') }}</option>
          <option v-for="member in members" :key="member" :value="member">
            {{ member }}
          </option>
        </select>
        <div class="action-toggle" role="radiogroup" :aria-label="t('web_operator_action')">
          <button
            v-for="action in ACTIONS"
            :key="action"
            type="button"
            class="action-chip"
            :class="[action.toLowerCase(), { active: operatorAction === action }]"
            :aria-pressed="operatorAction === action"
            :disabled="operatorSending"
            @click="operatorAction = action"
          >
            {{ action }}
          </button>
        </div>
      </div>

      <label class="sr-only" for="room-operator-payload">{{ t('web_operator_payload') }}</label>
      <textarea
        id="room-operator-payload"
        v-model="operatorPayload"
        rows="3"
        :placeholder="t('web_operator_placeholder')"
        :disabled="operatorSending"
      ></textarea>

      <div class="operator-footer">
        <p v-if="lastOperatorName" class="panel-note">
          {{ t('web_operator_sending_as').replace('{agent}', lastOperatorName) }}
        </p>
        <button class="primary-button" type="submit" :disabled="operatorSending || !operatorPayload.trim()">
          <span v-if="operatorSending" class="spinner" aria-hidden="true"></span>
          <RoomIcon v-else name="send" :size="14" />
          {{ t('web_operator_send') }}
        </button>
      </div>
    </form>

    <!-- Owner inbox: read the messages queued FOR the dashboard-controlled
         chief. Receiving consumes the message, exactly like the agent would. -->
    <section class="inbox">
      <div class="inbox-head">
        <strong class="inbox-title">{{ t('web_operator_inbox_title') }}</strong>
        <label class="inbox-listen">
          <input v-model="listening" type="checkbox" />
          {{ t('web_operator_inbox_listen') }}
        </label>
        <button class="secondary-button" type="button" :disabled="receiving" @click="receiveOnce(false)">
          <span v-if="receiving" class="spinner" aria-hidden="true"></span>
          <RoomIcon v-else name="inbox" :size="14" />
          {{ t('web_operator_inbox_receive') }}
        </button>
      </div>
      <p v-if="!inbox.length" class="panel-note">{{ t('web_operator_inbox_empty') }}</p>
      <ul v-else class="inbox-list">
        <li v-for="msg in inbox" :key="msg.id || msg.ts" class="inbox-item">
          <div class="inbox-meta">
            <span class="inbox-action" :class="(msg.action || 'info').toLowerCase()">{{ msg.action || 'INFO' }}</span>
            <span class="inbox-from">{{ msg.from }}</span>
            <span class="inbox-ts">{{ msg.ts ? new Date(msg.ts).toLocaleTimeString() : '' }}</span>
            <button
              class="inbox-reply"
              type="button"
              :title="t('web_operator_inbox_reply')"
              @click="replyTo(msg)"
            >
              <RoomIcon name="send" :size="12" />
            </button>
          </div>
          <p class="inbox-body">{{ msg.payload }}</p>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { sendSessionOperatorMessage, receiveSessionOperatorMessage, type OperatorInboxMessage } from '../../api/managed'
import { getApiErrorMessage } from '../../api/client'
import { useManagedI18n } from '../../i18n'
import { useToast } from '../../composables/useToast'
import RoomIcon from './RoomIcon.vue'

const ACTIONS = ['TASK', 'INFO', 'REPLY'] as const

const props = defineProps<{
  slug: string
  sessionId: string
  members: string[]
  /** Preselect a recipient (set when the user clicks "message" on a map node). */
  target?: string
}>()

const { t } = useManagedI18n()
const toast = useToast()

const operatorSending = ref(false)
const operatorTo = ref('all')
const operatorAction = ref<(typeof ACTIONS)[number]>('TASK')
const operatorPayload = ref('')
const lastOperatorName = ref('')

watch(
  () => props.members,
  value => {
    if (operatorTo.value !== 'all' && !value.includes(operatorTo.value)) {
      operatorTo.value = 'all'
    }
  },
)

watch(
  () => props.target,
  value => {
    if (value && props.members.includes(value)) {
      operatorTo.value = value
    }
  },
  { immediate: true },
)

// ── Owner inbox ──

const inbox = ref<OperatorInboxMessage[]>([])
const receiving = ref(false)
const listening = ref(false)
let listenTimer: ReturnType<typeof setInterval> | null = null

async function receiveOnce(silent = false) {
  if (receiving.value) return
  receiving.value = true
  try {
    const result = await receiveSessionOperatorMessage(props.slug, props.sessionId, { timeout_seconds: 0.5 })
    lastOperatorName.value = result.operator.agent_name
    if (result.status === 'delivered' && result.message) {
      inbox.value = [result.message, ...inbox.value].slice(0, 50)
    } else if (!silent) {
      toast.show(t('web_operator_inbox_empty'), 'info')
    }
  } catch (err) {
    // A conflict means the real agent is already listening for this identity —
    // stop the poll instead of fighting it for messages.
    listening.value = false
    if (!silent) toast.show(getApiErrorMessage(err), 'error')
  } finally {
    receiving.value = false
  }
}

watch(listening, active => {
  if (listenTimer) {
    clearInterval(listenTimer)
    listenTimer = null
  }
  if (active) {
    receiveOnce(true)
    listenTimer = setInterval(() => receiveOnce(true), 5000)
  }
})

onUnmounted(() => {
  if (listenTimer) clearInterval(listenTimer)
})

function replyTo(msg: OperatorInboxMessage) {
  if (msg.from && props.members.includes(msg.from)) {
    operatorTo.value = msg.from
  }
  operatorAction.value = 'REPLY'
}

async function handleSendOperatorMessage() {
  const body = operatorPayload.value.trim()
  if (!body) return
  operatorSending.value = true
  try {
    const result = await sendSessionOperatorMessage(props.slug, props.sessionId, {
      to: operatorTo.value,
      action: operatorAction.value,
      payload: body,
    })
    lastOperatorName.value = result.operator.agent_name
    operatorPayload.value = ''
    toast.show(t('web_operator_sent'), 'success')
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
  } finally {
    operatorSending.value = false
  }
}
</script>

<style scoped>
.room-panel-body { display: flex; flex-direction: column; gap: 12px; }
.operator-form { display: flex; flex-direction: column; gap: 10px; }
.operator-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.operator-label { color: var(--muted); font-size: 0.82rem; font-weight: 600; }
select {
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--soft);
  color: var(--ink);
  font-size: 0.88rem;
  min-width: 160px;
}
select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); outline: none; }
.action-toggle { display: inline-flex; gap: 6px; margin-left: auto; }
.action-chip {
  padding: 7px 14px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--soft);
  color: var(--muted);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.05em;
  cursor: pointer;
  transition: all 0.15s ease;
}
.action-chip.active.task { color: #EF9F27; border-color: rgba(239, 159, 39, 0.4); background: rgba(239, 159, 39, 0.1); }
.action-chip.active.info { color: #85B7EB; border-color: rgba(133, 183, 235, 0.4); background: rgba(133, 183, 235, 0.1); }
.action-chip.active.reply { color: #AFA9EC; border-color: rgba(175, 169, 236, 0.4); background: rgba(175, 169, 236, 0.1); }
.action-chip:disabled { opacity: 0.5; cursor: default; }
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
.operator-footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.panel-note { color: var(--muted); font-size: 0.8rem; margin: 0; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }

/* Owner inbox */
.inbox { display: flex; flex-direction: column; gap: 10px; padding-top: 12px; border-top: 1px solid var(--line); }
.inbox-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.inbox-title { font-size: 0.82rem; font-weight: 800; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
.inbox-listen { display: inline-flex; align-items: center; gap: 6px; margin-left: auto; color: var(--muted); font-size: 0.8rem; font-weight: 600; cursor: pointer; }
.inbox-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; max-height: 320px; overflow-y: auto; }
.inbox-item { border: 1px solid var(--line); border-radius: 12px; padding: 10px 12px; background: var(--card-bg-soft); }
.inbox-meta { display: flex; align-items: center; gap: 8px; }
.inbox-action { padding: 2px 8px; border-radius: 999px; font-size: 0.66rem; font-weight: 800; letter-spacing: 0.05em; border: 1px solid var(--line); color: var(--muted); }
.inbox-action.task { color: #EF9F27; border-color: rgba(239, 159, 39, 0.3); background: rgba(239, 159, 39, 0.08); }
.inbox-action.info { color: #85B7EB; border-color: rgba(133, 183, 235, 0.3); background: rgba(133, 183, 235, 0.08); }
.inbox-action.reply { color: #AFA9EC; border-color: rgba(175, 169, 236, 0.3); background: rgba(175, 169, 236, 0.08); }
.inbox-from { font-size: 0.8rem; font-weight: 700; color: var(--ink); }
.inbox-ts { font-size: 0.72rem; color: var(--muted); }
.inbox-reply { margin-left: auto; display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; padding: 0; border: 1px solid var(--line); border-radius: 8px; background: transparent; color: var(--muted); cursor: pointer; transition: all 0.15s ease; }
.inbox-reply:hover { color: var(--accent); border-color: var(--accent-glow); }
.inbox-body { margin: 8px 0 0; font-size: 0.86rem; line-height: 1.5; color: var(--ink); white-space: pre-wrap; word-break: break-word; }
@media (max-width: 720px) {
  .action-toggle { margin-left: 0; }
}
</style>
