import { useI18n as useSharedI18n, type Messages } from '@acp/shared'
import { es } from './es'
import { en } from './en'

const messages: Messages = { es, en }

export { messages }

export function useManagedI18n() {
  const { locale, setLocale, t: sharedT } = useSharedI18n(messages)

  function t(key: string, vars?: Record<string, string | number>): string {
    return sharedT(key, vars)
  }

  return { locale, setLocale, t }
}
