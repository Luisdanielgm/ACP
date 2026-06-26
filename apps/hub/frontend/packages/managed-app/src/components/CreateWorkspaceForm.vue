<template>
  <div :class="containerClass">
    <template v-if="layout === 'expanded'">
      <div class="create-copy">
        <h3>{{ t('admin_create_workspace') }}</h3>
        <p>{{ t('dash_create_workspace_help') }}</p>
      </div>
      <form class="create-form" @submit.prevent="onSubmit" novalidate>
        <div class="field">
          <label :for="nameId">{{ t('admin_workspace_name') }}</label>
          <input
            :id="nameId"
            v-model="workspaceName"
            type="text"
            :placeholder="t('admin_workspace_name_ph')"
            required
            :aria-required="true"
          />
        </div>
        <div class="field">
          <label :for="emailId">{{ t('admin_workspace_admin_email') }}</label>
          <input
            :id="emailId"
            v-model="adminEmail"
            type="email"
            :placeholder="t('admin_workspace_admin_email_ph')"
            :required="requireAdminEmail"
            :aria-required="requireAdminEmail"
          />
        </div>
        <p class="create-hint" role="status">
          <span v-if="isSelfAssign" class="hint-icon" aria-hidden="true">✓</span>
          <span v-else class="hint-icon" aria-hidden="true">✉</span>
          {{ isSelfAssign ? t('dash_create_self_hint') : t('dash_create_invite_hint') }}
        </p>
        <button type="submit" class="primary-button" :disabled="submitting">
          <span v-if="submitting" class="spinner" aria-hidden="true"></span>
          {{ submitting ? t('creating') : t('admin_create_submit') }}
        </button>
      </form>
    </template>

    <fieldset v-else class="compact-fieldset">
      <legend>{{ t('admin_create_workspace') }}</legend>
      <form class="inline-form create-row" @submit.prevent="onSubmit" novalidate>
        <label :for="nameId" class="sr-only">{{ t('admin_workspace_name') }}</label>
        <input
          :id="nameId"
          v-model="workspaceName"
          type="text"
          :placeholder="t('admin_workspace_name_ph')"
          required
          :aria-required="true"
        />
        <label :for="emailId" class="sr-only">{{ t('admin_workspace_admin_email') }}</label>
        <input
          :id="emailId"
          v-model="adminEmail"
          type="email"
          :placeholder="t('admin_workspace_admin_email_ph')"
          :required="requireAdminEmail"
        />
        <button type="submit" :disabled="submitting">
          <span v-if="submitting" class="spinner" aria-hidden="true"></span>
          {{ submitting ? t('creating') : t('admin_create_submit') }}
        </button>
      </form>
    </fieldset>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useManagedI18n } from '../i18n'

const props = withDefaults(
  defineProps<{
    submitting?: boolean
    /** Email of the signed-in user. Used to render the self-vs-invite hint. */
    currentUserEmail?: string
    /** "expanded" matches the Dashboard hero card; "compact" matches the
     *  inline admin top-bar fieldset. */
    layout?: 'expanded' | 'compact'
    requireAdminEmail?: boolean
  }>(),
  {
    submitting: false,
    currentUserEmail: '',
    layout: 'expanded',
    requireAdminEmail: true,
  },
)

const emit = defineEmits<{
  submit: [data: { name: string; admin_email: string }]
}>()

const { t } = useManagedI18n()

const workspaceName = ref('')
const adminEmail = ref('')

const nameId = `ws-create-name-${Math.random().toString(36).slice(2, 8)}`
const emailId = `ws-create-email-${Math.random().toString(36).slice(2, 8)}`

const containerClass = computed(() => (props.layout === 'expanded' ? 'create-card' : ''))

const isSelfAssign = computed(() => {
  const trimmed = adminEmail.value.trim().toLowerCase()
  const current = (props.currentUserEmail || '').trim().toLowerCase()
  return Boolean(trimmed) && trimmed === current
})

function onSubmit() {
  const name = workspaceName.value.trim()
  const email = adminEmail.value.trim().toLowerCase()
  if (!name) return
  if (props.requireAdminEmail && !email) return
  emit('submit', { name, admin_email: email })
}

defineExpose({
  reset: () => {
    workspaceName.value = ''
    adminEmail.value = ''
  },
})
</script>
