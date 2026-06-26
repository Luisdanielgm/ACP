function normalizeDateLabel(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  if (value instanceof Date) return value.toISOString()
  return ''
}

function parseTimestamp(value: unknown): number {
  if (value instanceof Date) return value.getTime()
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return NaN
    return value < 1e12 ? value * 1000 : value
  }
  if (typeof value !== 'string') return NaN
  const trimmed = value.trim()
  if (!trimmed) return NaN
  if (/^\d+$/.test(trimmed)) {
    const numeric = Number(trimmed)
    if (!Number.isFinite(numeric)) return NaN
    return numeric < 1e12 ? numeric * 1000 : numeric
  }
  return new Date(trimmed).getTime()
}

export function relativeTime(value: unknown, now = Date.now()): string {
  const ts = parseTimestamp(value)
  const fallback = normalizeDateLabel(value)
  if (isNaN(ts)) return fallback
  const diffMs = now - ts
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHr = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHr / 24)

  if (diffSec < 60) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  if (diffHr < 24) return `${diffHr}h ago`
  if (diffDay < 7) return `${diffDay}d ago`
  const iso = new Date(ts).toISOString()
  return iso.slice(0, 10)
}

export function formatAbsolute(value: unknown): string {
  const ts = parseTimestamp(value)
  const fallback = normalizeDateLabel(value)
  if (isNaN(ts)) return fallback
  return new Date(ts).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
