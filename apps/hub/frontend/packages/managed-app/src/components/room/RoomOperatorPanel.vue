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
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { sendSessionOperatorMessage } from '../../api/managed'
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
@media (max-width: 720px) {
  .action-toggle { margin-left: 0; }
}
</style>
