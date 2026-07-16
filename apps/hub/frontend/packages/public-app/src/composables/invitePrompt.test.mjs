import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('./invitePrompt.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2020, target: ts.ScriptTarget.ES2020 },
}).outputText
const { buildInvitePrompt } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

const payload = {
  session_id: 'session-1',
  join_code: 'JOIN42',
  hub_http: '',
  official_hub_http: '',
}

test('buildInvitePrompt creates a self-contained safe invitation for an external LLM agent', () => {
  const prompt = buildInvitePrompt(payload, 'en', 'https://room.example/')

  assert.match(prompt, /ACP client 0\.3\.16 or newer/)
  assert.match(prompt, /https:\/\/room\.example\/downloads\/ACP_AGENT\.zip/)
  assert.doesNotMatch(prompt, /(^|\n)curl\s/)
  assert.match(prompt, /urllib\.request\.Request/)
  assert.match(prompt, /python ACP_AGENT\/acp\.py --version/)
  assert.match(prompt, /update-check --hub-http "https:\/\/room\.example"/)
  assert.match(prompt, /self-update --hub-http "https:\/\/room\.example" --auto-when-idle/)
  assert.match(prompt, /git status --short -- ACP_AGENT/)
  assert.match(prompt, /dirty.*commit|dirty.*stash|commit.*stash/i)
  assert.match(prompt, /--allow-tracked-repo/)
  assert.match(prompt, /confirm.*0\.3\.16|0\.3\.16.*confirm/i)
  assert.match(prompt, /join-session --config ACP_AGENT\/agents\/<agent>\.json --agent <agent>/)
  assert.match(prompt, /--agent <agent>/)
  assert.match(prompt, /--hub-http "https:\/\/room\.example"/)
  assert.match(prompt, /--code "JOIN42"/)
  assert.match(prompt, /listen --agent <agent> --stop-after-message --timeout-seconds 300/)
  assert.match(prompt, /runner start --config ACP_AGENT\/agents\/<agent>\.json --agent <agent>/)
  assert.match(prompt, /--join-code "JOIN42"/)
  assert.match(prompt, /--provider <codex_local\|claude_local>/)
  assert.match(prompt, /--workspace "<ABSOLUTE_PROJECT_PATH>"/)
  assert.match(prompt, /--allow-sender "<TRUSTED_COORDINATOR>"/)
  assert.match(prompt, /--reply-to "<TRUSTED_COORDINATOR>"/)
  assert.doesNotMatch(prompt, /\\\s*$/m)
  assert.doesNotMatch(prompt, /listen --config ACP_AGENT\/agents\/<agent>\.json\s*$/m)
  assert.doesNotMatch(prompt, /member[_-]token|workspace[_-]token/i)
})

test('buildInvitePrompt fails closed when no real Hub origin is available', () => {
  assert.throws(
    () => buildInvitePrompt(payload, 'en', ''),
    /Hub HTTP origin is required/,
  )
})

test('buildInvitePrompt uses the current page origin instead of an empty payload origin', () => {
  const prompt = buildInvitePrompt(payload, 'es', 'https://acp.customer.test')

  assert.match(prompt, /--hub-http "https:\/\/acp\.customer\.test"/)
  assert.match(prompt, /\/downloads\/ACP_AGENT\.zip/)
  assert.match(prompt, /--stop-after-message --timeout-seconds 300/)
})
