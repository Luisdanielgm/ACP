import { ref, watchEffect, onMounted } from 'vue'

export type ThemeMode = 'dark' | 'light' | 'system'

const STORAGE_KEY = 'acp_dashboard_theme'

const theme = ref<ThemeMode>('system')

let initialized = false

function readStoredTheme(storageKey: string): ThemeMode | null {
  try {
    const stored = localStorage.getItem(storageKey)
    if (stored === 'dark' || stored === 'light' || stored === 'system') {
      return stored
    }
  } catch {
    // Storage can be unavailable in hardened browser contexts.
  }
  return null
}

function persistTheme(storageKey: string, mode: ThemeMode) {
  try {
    localStorage.setItem(storageKey, mode)
  } catch {
    // Ignore storage failures and keep the in-memory theme.
  }
}

function applyTheme(mode: ThemeMode) {
  document.documentElement.dataset.theme = mode
}

export function useTheme(storageKey = STORAGE_KEY) {
  if (!initialized) {
    const stored = readStoredTheme(storageKey)
    if (stored) {
      theme.value = stored
    }
    initialized = true
  }

  onMounted(() => applyTheme(theme.value))

  watchEffect(() => {
    applyTheme(theme.value)
    persistTheme(storageKey, theme.value)
  })

  function setTheme(mode: ThemeMode) {
    theme.value = mode
  }

  return { theme, setTheme }
}
