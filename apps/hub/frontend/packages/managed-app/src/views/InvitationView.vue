<template>
  <div class="invitation-page">
    <section class="topbar">
      <div class="brand"><span class="mark"></span><span>{{ t('login_title') }}</span></div>
      <div class="nav-actions">
        <ThemeToggle />
        <LangToggle :messages="messages" />
      </div>
    </section>

    <section class="invitation-card">
      <span class="kicker">{{ t('invitation_kicker') }}</span>
      <h1>{{ t('invitation_title') }}</h1>
      <p class="body">
        {{
          accepted
            ? t('invitation_redirecting_body')
            : (workspaceName ? t('invitation_body_for_workspace', { name: workspaceName }) : t('invitation_body'))
        }}
      </p>

      <form @submit.prevent="handleAccept" class="invitation-form">
        <label v-if="requiresPassword">
          <span>{{ t('invitation_password') }}</span>
          <input v-model="password" type="password" autocomplete="new-password" :disabled="loading || accepted" />
          <span class="hint">{{ t('invitation_password_help') }}</span>
        </label>
        <p v-else-if="previewReady" class="hint existing-account-hint">
          {{ t('invitation_existing_account_hint') }}
        </p>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button type="submit" :disabled="loading || !previewReady" class="primary-button">
          {{ loading || accepted ? t('invitation_redirecting') : t('invitation_accept') }}
        </button>
      </form>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ThemeToggle, LangToggle } from '@acp/shared'
import { useManagedI18n, messages } from '../i18n'
import { acceptInvitation, fetchInvitationPreview } from '../api/managed'

const route = useRoute()
const router = useRouter()
const { t } = useManagedI18n()

const token = computed(() => String(route.params.token))
const password = ref('')
const loading = ref(false)
const error = ref('')
const accepted = ref(false)
const previewReady = ref(false)
const requiresPassword = ref(true) // default to true so we don't accidentally hide the field if preview fails
const workspaceName = ref('')

onMounted(async () => {
  try {
    const preview = await fetchInvitationPreview(token.value)
    requiresPassword.value = preview.requires_password
    workspaceName.value = preview.workspace?.name ?? ''
  } catch (e: any) {
    // Preview failure is non-fatal: keep the password field visible and let
    // the accept call surface the real error (404/410/etc.) on submit.
    error.value = e?.message ?? t('invitation_error')
  } finally {
    previewReady.value = true
  }
})

async function handleAccept() {
  error.value = ''
  loading.value = true
  try {
    // Only send a password when the backend told us this principal needs one.
    const passwordToSend = requiresPassword.value ? (password.value || undefined) : undefined
    const result = await acceptInvitation(token.value, passwordToSend)
    accepted.value = true
    const target = new URL(result.redirect_url, window.location.origin)
    target.searchParams.set('flash', 'invitation-accepted')
    await router.replace(target.pathname + target.search + target.hash)
  } catch (e: any) {
    error.value = e?.message ?? t('invitation_error')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.invitation-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}
.invitation-page::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 700px;
  height: 700px;
  background: radial-gradient(circle, var(--accent-subtle) 0%, transparent 70%);
  pointer-events: none;
  animation: hero-glow 6s ease-in-out infinite;
}
@keyframes hero-glow {
  0%, 100% { opacity: 0.5; transform: translate(-50%, -50%) scale(1); }
  50% { opacity: 0.9; transform: translate(-50%, -50%) scale(1.15); }
}

.topbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 28px;
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border-bottom: 1px solid var(--glass-border);
  position: relative;
  z-index: 1;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 700;
  font-size: 1rem;
  color: var(--text-1);
  letter-spacing: -0.01em;
}
.mark {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 12px var(--accent-glow);
  animation: brand-pulse 3s ease-in-out infinite;
}
@keyframes brand-pulse {
  0%, 100% { box-shadow: 0 0 12px var(--accent-glow); }
  50% { box-shadow: 0 0 20px var(--accent-glow); }
}
.nav-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
}

.invitation-card, .result-card {
  max-width: 460px;
  margin: 60px auto;
  padding: 36px;
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xl);
  position: relative;
  z-index: 1;
  animation: card-enter var(--transition-spring);
}
@keyframes card-enter {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}
.invitation-card:hover {
  border-color: var(--accent-glow);
  box-shadow: var(--shadow-lg), 0 0 50px var(--accent-subtle);
}
.kicker {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--accent);
  font-weight: 600;
}
.invitation-card h1 {
  margin: 10px 0 14px;
  font-size: 1.6rem;
  color: var(--text-1);
  letter-spacing: -0.03em;
  font-weight: 800;
}
.body {
  color: var(--text-2);
  font-size: 0.92rem;
  line-height: 1.6;
  margin-bottom: 28px;
}

.invitation-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.invitation-form label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 0.86rem;
  color: var(--text-2);
  font-weight: 500;
}
.invitation-form input {
  padding: 12px 14px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--surface-0);
  color: var(--text-1);
  font-size: 0.92rem;
  transition: all var(--transition-fast);
}
.invitation-form input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
}
.invitation-form input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.hint {
  font-size: 0.78rem;
  color: var(--text-3);
  line-height: 1.4;
}
.error {
  color: var(--danger);
  font-size: 0.86rem;
  margin: 0;
  padding: 10px 14px;
  background: var(--danger-subtle);
  border-radius: var(--radius-md);
  border: 1px solid var(--danger-glow);
  animation: shake 0.4s ease-in-out;
}
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-4px); }
  75% { transform: translateX(4px); }
}
.primary-button {
  padding: 13px 22px;
  background: var(--accent);
  color: var(--button-accent-text);
  border: none;
  border-radius: var(--radius-md);
  font-weight: 700;
  cursor: pointer;
  font-size: 0.92rem;
  text-align: center;
  transition: all var(--transition-spring);
  position: relative;
  overflow: hidden;
}
.primary-button::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(255,255,255,0.2), transparent);
  opacity: 0;
  transition: opacity var(--transition-fast);
}
.primary-button:hover::after {
  opacity: 1;
}
.primary-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.primary-button:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 24px var(--accent-glow);
}
.primary-button:active:not(:disabled) {
  transform: scale(0.97);
}
.primary-button:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--accent-subtle);
}

.success h1 {
  color: var(--text-1);
  font-size: 1.4rem;
  font-weight: 800;
  letter-spacing: -0.02em;
}
.success p {
  color: var(--text-2);
  margin: 14px 0 24px;
  line-height: 1.6;
}

@media (max-width: 540px) {
  .invitation-card, .result-card {
    margin: 30px 16px;
    padding: 28px 24px;
  }
  .topbar {
    padding: 12px 16px;
    gap: 10px;
  }
}
</style>