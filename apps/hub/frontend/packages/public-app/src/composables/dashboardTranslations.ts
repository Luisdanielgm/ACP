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

// ── Display-name localization ──
// Agent display names come from the agent's REAL name tokens ("Chief",
// "People Manager"), which are usually English. When the UI runs in Spanish,
// translate the common role phrases/words; anything unknown stays as-is.
const ES_PHRASES: Record<string, string> = {
  'people manager': 'Gerente de Personal',
  'finance analyst': 'Analista de Finanzas',
  'data analyst': 'Analista de Datos',
  'ops agent': 'Agente de Operaciones',
  'operations agent': 'Agente de Operaciones',
  'support agent': 'Agente de Soporte',
  'product manager': 'Gerente de Producto',
  'project manager': 'Gerente de Proyecto',
  'frontend developer': 'Desarrollador Frontend',
  'backend developer': 'Desarrollador Backend',
  'human resources': 'Recursos Humanos',
  'customer success': 'Éxito del Cliente',
}

const ES_WORDS: Record<string, string> = {
  chief: 'Jefe',
  leader: 'Líder',
  coordinator: 'Coordinador',
  manager: 'Gerente',
  agent: 'Agente',
  worker: 'Trabajador',
  assistant: 'Asistente',
  analyst: 'Analista',
  developer: 'Desarrollador',
  designer: 'Diseñador',
  engineer: 'Ingeniero',
  researcher: 'Investigador',
  writer: 'Redactor',
  reviewer: 'Revisor',
  tester: 'Probador',
  support: 'Soporte',
  finance: 'Finanzas',
  operations: 'Operaciones',
  ops: 'Operaciones',
  sales: 'Ventas',
  security: 'Seguridad',
  legal: 'Legal',
  research: 'Investigación',
  people: 'Personal',
}

export function translateDisplayName(locale: string, label: string): string {
  if (locale !== 'es') return label
  const lower = label.toLowerCase()
  if (ES_PHRASES[lower]) return ES_PHRASES[lower]
  return label
    .split(/\s+/)
    .map(word => {
      const hit = ES_WORDS[word.toLowerCase()]
      return hit || word
    })
    .join(' ')
}
