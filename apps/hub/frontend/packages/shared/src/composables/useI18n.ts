import { ref, computed } from 'vue'

export type Locale = 'es' | 'en'
export type Messages = Record<string, Record<string, string>>

const STORAGE_KEY = 'acp_dashboard_lang'

const locale = ref<Locale>('es')

let initialized = false

function readStoredLocale(storageKey: string): Locale | null {
  try {
    const stored = localStorage.getItem(storageKey)
    if (stored === 'es' || stored === 'en') {
      return stored
    }
  } catch {
    // Storage can be unavailable in hardened browser contexts.
  }
  return null
}

function persistLocale(storageKey: string, lang: Locale) {
  try {
    localStorage.setItem(storageKey, lang)
  } catch {
    // Ignore storage failures and keep the in-memory locale.
  }
}

export function useI18n(messages: Messages, storageKey = STORAGE_KEY) {
  if (!initialized) {
    const stored = readStoredLocale(storageKey)
    if (stored) {
      locale.value = stored
    }
    initialized = true
  }

  function t(key: string, vars?: Record<string, string | number>): string {
    const dict = messages[locale.value] ?? messages.es ?? {}
    let text = dict[key] ?? key
    if (vars) {
      for (const [k, v] of Object.entries(vars)) {
        text = text.replace(`{${k}}`, String(v))
      }
    }
    return text
  }

  function setLocale(lang: Locale) {
    locale.value = lang
    persistLocale(storageKey, lang)
  }

  return { locale, t, setLocale }
}
