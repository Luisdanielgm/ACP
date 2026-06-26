<template>
  <section
    v-if="visible"
    class="onboarding-checklist surface-card"
    role="region"
    :aria-label="t('onboarding_title')"
  >
    <div class="onboarding-header">
      <div>
        <span class="section-chip section-chip-accent">{{ t('onboarding_kicker') }}</span>
        <h2>{{ t('onboarding_title') }}</h2>
        <p>{{ t('onboarding_body') }}</p>
      </div>
      <button
        type="button"
        class="onboarding-dismiss"
        @click="dismiss"
        :aria-label="t('onboarding_dismiss')"
      >
        &times;
      </button>
    </div>

    <ol class="onboarding-steps">
      <li
        v-for="step in steps"
        :key="step.id"
        :class="{ 'step-done': step.done, 'step-current': !step.done && step.id === currentStepId }"
      >
        <span class="step-marker" aria-hidden="true">
          <span v-if="step.done" class="step-check">&#10003;</span>
          <span v-else class="step-number">{{ step.index }}</span>
        </span>
        <div class="step-body">
          <p class="step-title">{{ step.title }}</p>
          <p class="step-body-text">{{ step.body }}</p>
        </div>
      </li>
    </ol>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue'
import { useManagedI18n } from '../i18n'

const props = defineProps<{
  workspaceSlug: string
  hasActiveToken: boolean
  hasSessions: boolean
}>()

const { t } = useManagedI18n()

const STORAGE_PREFIX = 'acp.managed.onboarding.dismissed:'
const dismissed = ref(false)

function storageKey() {
  return STORAGE_PREFIX + props.workspaceSlug
}

function readDismissed(): boolean {
  if (typeof window === 'undefined') return false
  try {
    return window.localStorage.getItem(storageKey()) === '1'
  } catch {
    return false
  }
}

function persistDismissed() {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(storageKey(), '1')
  } catch {
    // ignore quota / privacy errors
  }
}

onMounted(() => {
  dismissed.value = readDismissed()
})

watch(
  () => props.workspaceSlug,
  () => {
    dismissed.value = readDismissed()
  },
)

interface Step {
  id: string
  index: number
  title: string
  body: string
  done: boolean
}

const steps = computed<Step[]>(() => [
  {
    id: 'workspace_assigned',
    index: 1,
    title: t('onboarding_step_workspace_title'),
    body: t('onboarding_step_workspace_body'),
    done: true, // landing here means the workspace is already assigned
  },
  {
    id: 'rotate_token',
    index: 2,
    title: t('onboarding_step_rotate_token_title'),
    body: t('onboarding_step_rotate_token_body'),
    done: props.hasActiveToken,
  },
  {
    id: 'create_session',
    index: 3,
    title: t('onboarding_step_create_session_title'),
    body: t('onboarding_step_create_session_body'),
    done: props.hasSessions,
  },
])

const currentStepId = computed(() => {
  const next = steps.value.find(step => !step.done)
  return next ? next.id : ''
})

const allDone = computed(() => steps.value.every(step => step.done))

// Show the checklist whenever there is at least one outstanding step and the
// user has not dismissed it for this workspace.
const visible = computed(() => !dismissed.value && !allDone.value)

function dismiss() {
  dismissed.value = true
  persistDismissed()
}
</script>

<style scoped>
.onboarding-checklist {
  padding: 20px 24px;
  margin-bottom: 20px;
  border: 1px solid var(--accent-subtle, var(--glass-border));
  background: var(--glass-bg);
  border-radius: var(--radius-xl);
}
.onboarding-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}
.onboarding-header h2 {
  margin: 6px 0 4px;
  font-size: 1.05rem;
  font-weight: 700;
}
.onboarding-header p {
  margin: 0;
  color: var(--text-2);
  font-size: 0.86rem;
  line-height: 1.5;
}
.onboarding-dismiss {
  background: transparent;
  border: none;
  color: var(--text-2);
  cursor: pointer;
  font-size: 1.4rem;
  line-height: 1;
  padding: 0 6px;
  border-radius: var(--radius-sm, 4px);
}
.onboarding-dismiss:hover {
  color: var(--text-1);
  background: var(--surface-1);
}
.onboarding-steps {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 10px;
}
.onboarding-steps li {
  display: grid;
  grid-template-columns: 32px 1fr;
  gap: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: var(--surface-1);
  border: 1px solid var(--border);
  transition: border-color var(--transition-fast), background var(--transition-fast);
}
.onboarding-steps li.step-current {
  border-color: var(--accent);
  background: var(--accent-subtle, var(--surface-1));
}
.onboarding-steps li.step-done {
  opacity: 0.72;
}
.step-marker {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--surface-2);
  color: var(--text-2);
  font-weight: 600;
}
.step-done .step-marker {
  background: var(--accent);
  color: var(--button-accent-text, white);
}
.step-current .step-marker {
  background: var(--accent);
  color: var(--button-accent-text, white);
}
.step-number {
  font-size: 0.86rem;
}
.step-check {
  font-size: 0.95rem;
  line-height: 1;
}
.step-title {
  margin: 0 0 4px;
  font-weight: 600;
  color: var(--text-1);
  font-size: 0.92rem;
}
.step-body-text {
  margin: 0;
  color: var(--text-2);
  font-size: 0.82rem;
  line-height: 1.45;
}
</style>
