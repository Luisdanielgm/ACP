// ACP dashboard asset registry.
// Assets live in this package (public-app) and are consumed by managed-app via the
// `@acp/public-app` source alias, so we resolve URLs with import.meta.glob — that works
// in both build roots without a shared /public directory.

type UrlMap = Record<string, string>

function basename(path: string): string {
  const file = path.split('/').pop() || ''
  return file.replace(/\.[^.]+$/, '')
}

// Strip the numeric ordering prefix ("01-leader-coordinator" -> "leader-coordinator").
function stripPrefix(name: string): string {
  return name.replace(/^\d+-/, '')
}

function byId(glob: UrlMap): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [path, url] of Object.entries(glob)) {
    out[stripPrefix(basename(path))] = url
  }
  return out
}

function byName(glob: UrlMap): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [path, url] of Object.entries(glob)) {
    out[basename(path)] = url
  }
  return out
}

const avatars256 = byId(import.meta.glob('./avatars/256/*.webp', { eager: true, query: '?url', import: 'default' }) as UrlMap)
const avatars512 = byId(import.meta.glob('./avatars/512/*.webp', { eager: true, query: '?url', import: 'default' }) as UrlMap)
const objects128 = byId(import.meta.glob('./objects/128/*.webp', { eager: true, query: '?url', import: 'default' }) as UrlMap)
const objects256 = byId(import.meta.glob('./objects/256/*.webp', { eager: true, query: '?url', import: 'default' }) as UrlMap)
const stateIcons = byName(import.meta.glob('./icons/*.svg', { eager: true, query: '?url', import: 'default' }) as UrlMap)

// ── Named avatar ids ──
export const AVATAR_LEADER = 'leader-coordinator'
export const AVATAR_HUMAN = 'human-observer'

// Robot avatars usable for generic agents (everything except the leader + human portraits),
// in a stable order so a name-hash lands on a consistent face.
export const ROBOT_AVATAR_IDS: string[] = Object.keys(avatars256)
  .filter(id => id !== AVATAR_LEADER && id !== AVATAR_HUMAN)
  .sort()

export function avatarUrl(id: string, size: 256 | 512 = 256): string {
  const table = size === 512 ? avatars512 : avatars256
  return table[id] || table[AVATAR_LEADER] || ''
}

export function stateIconUrl(name: string): string {
  return stateIcons[name] || ''
}

export function objectUrl(id: string, size: 128 | 256 = 256): string {
  const table = size === 256 ? objects256 : objects128
  return table[id] || ''
}

export const CROWN_URL = objectUrl('leader-crown', 128)
