import type { SessionEvent } from '../api/sessions'

// Delivery delay per message, derived ONLY from timestamps the hub already
// records: MESSAGE_SENT (message reached the hub) -> MESSAGE_DELIVERED (the
// recipient picked it up) -> MESSAGE_ACKNOWLEDGED. Nothing is measured on the
// client, so the numbers are hub-side and cover the whole send->pickup path.
// Limits: bounded by the history window the hub returns; a message still
// waiting has no delivery yet (deliveryMs === null).

export interface MessageLatency {
  messageId: string
  from: string
  to: string
  action: string
  sentAt: string
  deliveredAt: string | null
  deliveryMs: number | null
  acknowledgedAt: string | null
  ackMs: number | null
}

export interface MemberLatencyStats {
  receivedCount: number
  pendingCount: number
  avgReceiveMs: number | null
  maxReceiveMs: number | null
  lastReceiveMs: number | null
  sentCount: number
  avgSentMs: number | null
}

export function latencyKey(messageId: string, target: string): string {
  return `${messageId}:${target}`
}

function ms(ts: unknown): number | null {
  const parsed = Date.parse(String(ts || ''))
  return Number.isNaN(parsed) ? null : parsed
}

function mid(event: SessionEvent): string {
  return String((event as Record<string, unknown>).message_id || '')
}

export function messageLatencies(history: SessionEvent[]): MessageLatency[] {
  const byKey = new Map<string, MessageLatency>()
  const order: string[] = []
  for (const event of history || []) {
    const name = String(event.event || '').toUpperCase()
    const id = mid(event)
    if (!id) continue
    const target = String(event.target || '')
    const key = latencyKey(id, target)
    if (name === 'MESSAGE_SENT') {
      if (byKey.has(key)) continue
      byKey.set(key, {
        messageId: id,
        from: String(event.actor || ''),
        to: target,
        action: String(event.action || event.message_action || ''),
        sentAt: String(event.ts || ''),
        deliveredAt: null,
        deliveryMs: null,
        acknowledgedAt: null,
        ackMs: null,
      })
      order.push(key)
    } else if (name === 'MESSAGE_DELIVERED') {
      const item = byKey.get(key)
      const sent = item ? ms(item.sentAt) : null
      const at = ms(event.ts)
      if (item && !item.deliveredAt && sent !== null && at !== null) {
        item.deliveredAt = String(event.ts)
        item.deliveryMs = Math.max(0, at - sent)
      }
    } else if (name === 'MESSAGE_ACKNOWLEDGED') {
      const item = byKey.get(key)
      const sent = item ? ms(item.sentAt) : null
      const at = ms(event.ts)
      if (item && !item.acknowledgedAt && sent !== null && at !== null) {
        item.acknowledgedAt = String(event.ts)
        item.ackMs = Math.max(0, at - sent)
      }
    }
  }
  return order.map(key => byKey.get(key)!)
}

export function latencyIndex(latencies: MessageLatency[]): Map<string, MessageLatency> {
  const map = new Map<string, MessageLatency>()
  for (const item of latencies) map.set(latencyKey(item.messageId, item.to), item)
  return map
}

function avg(values: number[]): number | null {
  return values.length ? Math.round(values.reduce((a, b) => a + b, 0) / values.length) : null
}

export function memberLatencyMap(latencies: MessageLatency[]): Map<string, MemberLatencyStats> {
  const received = new Map<string, MessageLatency[]>()
  const sent = new Map<string, MessageLatency[]>()
  for (const item of latencies) {
    if (item.to) received.set(item.to, [...(received.get(item.to) || []), item])
    if (item.from) sent.set(item.from, [...(sent.get(item.from) || []), item])
  }
  const names = new Set([...received.keys(), ...sent.keys()])
  const result = new Map<string, MemberLatencyStats>()
  for (const name of names) {
    const rx = received.get(name) || []
    const tx = sent.get(name) || []
    const rxDone = rx.filter(i => i.deliveryMs !== null)
    const rxMs = rxDone.map(i => i.deliveryMs as number)
    const txMs = tx.filter(i => i.deliveryMs !== null).map(i => i.deliveryMs as number)
    result.set(name, {
      receivedCount: rx.length,
      pendingCount: rx.length - rxDone.length,
      avgReceiveMs: avg(rxMs),
      maxReceiveMs: rxMs.length ? Math.max(...rxMs) : null,
      lastReceiveMs: rxDone.length ? (rxDone[rxDone.length - 1].deliveryMs as number) : null,
      sentCount: tx.length,
      avgSentMs: avg(txMs),
    })
  }
  return result
}

export function formatDelay(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-'
  if (value < 1000) return `${Math.round(value)} ms`
  const seconds = value / 1000
  if (seconds < 60) return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)} s`
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds % 60)
  if (minutes < 60) return `${minutes}m ${String(rest).padStart(2, '0')}s`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ${String(minutes % 60).padStart(2, '0')}m`
}
