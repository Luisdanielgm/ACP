<template>
  <div class="login-page">
    <section class="topbar">
      <div class="brand"><span class="mark"></span><span>{{ t('login_title') }}</span></div>
      <div class="nav-links">
        <a href="/">{{ t('nav_landing') }}</a>
        <a href="/downloads">{{ t('nav_downloads') }}</a>
      </div>
      <div class="nav-actions">
        <ThemeToggle />
        <LangToggle :messages="messages" />
      </div>
    </section>

    <section class="login-card">
      <span class="kicker">{{ t('login_kicker') }}</span>
      <h1>{{ t('login_title') }}</h1>
      <p class="login-body">{{ t('login_body') }}</p>

      <form @submit.prevent="handleLogin" class="login-form">
        <label>
          <span>{{ t('login_email') }}</span>
          <input v-model="email" type="email" required autocomplete="email" />
        </label>
        <label>
          <span>{{ t('login_password') }}</span>
          <input v-model="password" type="password" required autocomplete="current-password" />
        </label>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button type="submit" :disabled="loading" class="primary-button">
          {{ loading ? t('login_loading') : t('login_submit') }}
        </button>
      </form>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ThemeToggle, LangToggle } from '@acp/shared'
import { useManagedAuth } from '../composables/useManagedAuth'
import { useManagedI18n, messages } from '../i18n'
import { ApiError } from '../api/client'

const route = useRoute()
const router = useRouter()
const { login, checkSession, managedHomePathFor } = useManagedAuth()
const { t } = useManagedI18n()

const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

function resolveRedirectPath(fallback = '/managed/dashboard'): string {
  const redirect = String(route.query.redirect ?? '').trim()
  if (!redirect || !redirect.startsWith('/') || redirect.startsWith('//')) {
    return fallback
  }
  return redirect
}

function mapQueryError(value: string): string {
  const raw = value.trim().toLowerCase()
  if (!raw) return ''
  if (raw === 'rate_limited') return t('login_rate_limited')
  // Default fallback for "1" or any other legacy value.
  return t('login_error')
}

onMounted(async () => {
  const queryError = String(route.query.error ?? '').trim()
  if (queryError) {
    error.value = mapQueryError(queryError)
  }
  const user = await checkSession(true)
  if (user) router.replace(resolveRedirectPath(managedHomePathFor(user)))
})

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    const result = await login(email.value, password.value)
    router.push(resolveRedirectPath(result.redirect_url ?? managedHomePathFor(result)))
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      error.value = t('login_error')
    } else {
      error.value = t('error_generic')
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}
.login-page::before {
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
.nav-links {
  display: flex;
  gap: 4px;
}
.nav-links a {
  color: var(--text-2);
  text-decoration: none;
  font-size: 0.86rem;
  padding: 6px 12px;
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
}
.nav-links a:hover {
  background: var(--surface-2);
  color: var(--text-1);
}
.nav-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
}

.login-card {
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
.login-card:hover {
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
.login-card h1 {
  margin: 10px 0 14px;
  font-size: 1.6rem;
  color: var(--text-1);
  letter-spacing: -0.03em;
  font-weight: 800;
}
.login-body {
  color: var(--text-2);
  font-size: 0.92rem;
  line-height: 1.6;
  margin-bottom: 28px;
}
.login-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.login-form label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 0.86rem;
  color: var(--text-2);
  font-weight: 500;
}
.login-form input {
  padding: 12px 14px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--surface-0);
  color: var(--text-1);
  font-size: 0.92rem;
  transition: all var(--transition-fast);
}
.login-form input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
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

@media (max-width: 540px) {
  .login-card {
    margin: 30px 16px;
    padding: 28px 24px;
  }
  .topbar {
    padding: 12px 16px;
    gap: 10px;
  }
  .nav-links {
    display: none;
  }
}
</style>
