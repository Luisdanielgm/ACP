import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('./latency.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2020, target: ts.ScriptTarget.ES2020 },
}).outputText
const { messageLatencies, memberLatencyMap, latencyIndex, formatDelay } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
)

const history = [
  { event: 'MESSAGE_SENT', actor: 'boss', target: 'a', action: 'TASK', message_id: 'm1', ts: '2026-01-01T00:00:00.000Z' },
  { event: 'MESSAGE_DELIVERED', actor: 'boss', target: 'a', message_id: 'm1', ts: '2026-01-01T00:00:02.500Z' },
  { event: 'MESSAGE_ACKNOWLEDGED', actor: 'boss', target: 'a', message_id: 'm1', ts: '2026-01-01T00:00:03.000Z' },
  { event: 'MESSAGE_SENT', actor: 'boss', target: 'b', action: 'TASK', message_id: 'm1', ts: '2026-01-01T00:00:00.000Z' },
  { event: 'MESSAGE_SENT', actor: 'a', target: 'boss', action: 'REPLY', message_id: 'm2', ts: '2026-01-01T00:01:00.000Z' },
  { event: 'MESSAGE_DELIVERED', actor: 'a', target: 'boss', message_id: 'm2', ts: '2026-01-01T00:01:00.400Z' },
  { event: 'HEARTBEAT', actor: 'a', ts: '2026-01-01T00:01:01.000Z' },
]

test('pairs sent/delivered/ack per recipient from existing event timestamps', () => {
  const items = messageLatencies(history)
  assert.equal(items.length, 3)
  const toA = latencyIndex(items).get('m1:a')
  assert.equal(toA.deliveryMs, 2500)
  assert.equal(toA.ackMs, 3000)
  const toB = latencyIndex(items).get('m1:b')
  assert.equal(toB.deliveryMs, null)
  assert.equal(toB.deliveredAt, null)
})

test('aggregates receive and send delay per member and counts pending', () => {
  const stats = memberLatencyMap(messageLatencies(history))
  assert.equal(stats.get('a').avgReceiveMs, 2500)
  assert.equal(stats.get('a').avgSentMs, 400)
  assert.equal(stats.get('b').pendingCount, 1)
  assert.equal(stats.get('b').avgReceiveMs, null)
  assert.equal(stats.get('boss').sentCount, 2)
  assert.equal(stats.get('boss').avgSentMs, 2500)
})

test('negative skew is clamped and ids without a sent event are ignored', () => {
  const items = messageLatencies([
    { event: 'MESSAGE_SENT', actor: 'x', target: 'y', message_id: 'k', ts: '2026-01-01T00:00:05Z' },
    { event: 'MESSAGE_DELIVERED', actor: 'x', target: 'y', message_id: 'k', ts: '2026-01-01T00:00:04Z' },
    { event: 'MESSAGE_DELIVERED', actor: 'x', target: 'y', message_id: 'orphan', ts: '2026-01-01T00:00:04Z' },
  ])
  assert.equal(items.length, 1)
  assert.equal(items[0].deliveryMs, 0)
})

test('formatDelay is compact and human readable', () => {
  assert.equal(formatDelay(null), '-')
  assert.equal(formatDelay(120), '120 ms')
  assert.equal(formatDelay(2500), '2.5 s')
  assert.equal(formatDelay(42000), '42 s')
  assert.equal(formatDelay(125000), '2m 05s')
  assert.equal(formatDelay(3720000), '1h 02m')
})
