import { normalizedRole } from './sessionHelpers'

// Small i18n-dependent translation helpers shared by the dashboard section
// components. Extracted verbatim from SessionDashboardView.vue so multiple
// components (SquadMap, MemberLanes, MemberRoster, EventTimeline) can reuse
// them without duplicating the branching logic. Each component still owns
// its own `t` (from `useI18n`), which is passed in explicitly.
export type Translator = (key: string, vars?: Record<string, string | number>) => string

export function translateStatus(t: Translator, value: string | undefined): string {
  const s = String(value || '').toLowerCase()
  if (s === 'idle') return t('sd_idle_status')
  if (s === 'waiting') return t('sd_waiting_status')
  if (s === 'busy') return t('sd_busy_status')
  return value || '-'
}

export function translateRole(t: Translator, value: string | undefined): string {
  const r = normalizedRole(value)
  if (r === 'chief') return t('sd_role_chief')
  if (r === 'collaborator') return t('sd_role_collaborator')
  return t('sd_role_member')
}

export function translateDelivery(t: Translator, value: string | undefined): string {
  const d = String(value || '').toLowerCase()
  if (d === 'attached') return t('sd_delivery_attached')
  if (d === 'runner') return t('sd_delivery_runner')
  if (d === 'immediate') return t('sd_delivery_immediate')
  if (d === 'queued') return t('sd_delivery_queued')
  if (d === 'dequeued') return t('sd_delivery_dequeued')
  return value || '-'
}

export function translateEvent(t: Translator, value: string | undefined): string {
  const key = `sd_event_${value || ''}`
  const result = t(key)
  return result !== key ? result : (value || '-')
}
