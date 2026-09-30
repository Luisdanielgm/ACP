import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('./invitePrompt.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2020, target: ts.ScriptTarget.ES2020 },
}).outputText
const { buildInvitePrompt, buildDangerousUpdatePrompt, inviteJoinCode } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
)

const payload = {
  session_id: 'session-1',
  join_code: 'JOIN42',
  hub_http: '',
  official_hub_http: '',
}

test('full prompt installs from scratch, joins with --code-env and never contains the dangerous override', () => {
  const prompt = buildInvitePrompt(payload, 'en', 'https://room.example/', 'full')

  assert.match(prompt, /ACP client 0\.3\.16 or newer/)
  assert.match(prompt, /https:\/\/room\.example\/downloads\/ACP_AGENT\.zip/)
  assert.doesNotMatch(prompt, /(^|\n)curl\s/)
  assert.match(prompt, /urllib\.request\.Request/)
  assert.match(prompt, /python ACP_AGENT\/acp\.py --version/)
  assert.match(prompt, /update-check --hub-http "https:\/\/room\.example"/)
  assert.match(prompt, /self-update --hub-http "https:\/\/room\.example" --auto-when-idle/)
  assert.match(prompt, /join-session --config ACP_AGENT\/agents\/<agent>\.json --agent <agent>/)
  assert.match(prompt, /--hub-http "https:\/\/room\.example"/)
  assert.match(prompt, /--code-env ACP_JOIN_CODE/)
  assert.match(prompt, /listen --agent <agent> --stop-after-message --timeout-seconds 300/)
  assert.match(prompt, /runner start --config ACP_AGENT\/agents\/<agent>\.json --agent <agent>/)
  assert.match(prompt, /--provider <codex_local\|claude_local>/)
  assert.match(prompt, /--allow-sender "<TRUSTED_COORDINATOR>"/)
  // dangerous mode is separate
  assert.doesNotMatch(prompt, /--allow-tracked-repo/)
  assert.doesNotMatch(prompt, /update_from_release/)
  assert.doesNotMatch(prompt, /\\\s*$/m)
  assert.doesNotMatch(prompt, /member[_-]token|workspace[_-]token/i)
})

test('short prompt is join + listen only, for someone who already has the client', () => {
  const prompt = buildInvitePrompt(payload, 'en', 'https://room.example/', 'short')

  assert.match(prompt, /already have ACP client 0\.3\.16/)
  assert.match(prompt, /join-session .*--code-env ACP_JOIN_CODE/)
  assert.match(prompt, /listen --agent <agent> --stop-after-message --timeout-seconds 300/)
  assert.doesNotMatch(prompt, /ACP_AGENT\.zip/)
  assert.doesNotMatch(prompt, /self-update|update-check|update_from_release|--allow-tracked-repo/)
  assert.doesNotMatch(prompt, /runner start/)
  assert.ok(prompt.split('\n').length < buildInvitePrompt(payload, 'en', 'https://room.example/', 'full').split('\n').length)
})

test('both prompts label the code as a real secret and document per-OS env storage and length check', () => {
  for (const lang of ['en', 'es']) {
    for (const variant of ['short', 'full']) {
      const prompt = buildInvitePrompt(payload, lang, 'https://room.example', variant)
      assert.match(prompt, lang === 'en' ? /REAL join code.*secret/is : /codigo de union REAL.*secreto/is)
      assert.match(prompt, /export ACP_JOIN_CODE='JOIN42'/)
      assert.match(prompt, /\$env:ACP_JOIN_CODE = 'JOIN42'/)
      assert.match(prompt, /set "ACP_JOIN_CODE=JOIN42"/)
      assert.match(prompt, /print\(len\(os\.environ\['ACP_JOIN_CODE'\]\)\)/)
      assert.match(prompt, /--code-file/)
      assert.match(prompt, /--show-secrets/)
      assert.match(prompt, /--to-file/)
      assert.match(prompt, /--exec/)
      assert.match(prompt, /operator_approval/)
    }
  }
})

test('the dangerous update prompt is separate, warns loudly and carries no join code', () => {
  const prompt = buildDangerousUpdatePrompt(payload, 'en', 'https://room.example')
  assert.match(prompt, /DANGER/)
  assert.match(prompt, /OVERWRITE/)
  assert.match(prompt, /git status --short -- ACP_AGENT/)
  assert.match(prompt, /explicit approval/i)
  assert.match(prompt, /--allow-tracked-repo/)
  assert.doesNotMatch(prompt, /JOIN42/)
  assert.match(buildDangerousUpdatePrompt(payload, 'es', 'https://room.example'), /PELIGRO/)
})

test('unsafe join codes fall back to a placeholder instead of being embedded in shell lines', () => {
  const prompt = buildInvitePrompt({ ...payload, join_code: "x'; rm -rf /" }, 'en', 'https://room.example', 'short')
  assert.doesNotMatch(prompt, /rm -rf/)
  assert.match(prompt, /export ACP_JOIN_CODE='<JOIN_CODE>'/)
})

test('inviteJoinCode returns only the trimmed code', () => {
  assert.equal(inviteJoinCode({ join_code: '  ABCD1234 ' }), 'ABCD1234')
  assert.equal(inviteJoinCode({}), '')
})

test('buildInvitePrompt fails closed when no real Hub origin is available', () => {
  assert.throws(() => buildInvitePrompt(payload, 'en', ''), /Hub HTTP origin is required/)
  assert.throws(() => buildDangerousUpdatePrompt(payload, 'en', ''), /Hub HTTP origin is required/)
})

test('buildInvitePrompt uses the current page origin instead of an empty payload origin', () => {
  const prompt = buildInvitePrompt(payload, 'es', 'https://acp.customer.test')

  assert.match(prompt, /--hub-http "https:\/\/acp\.customer\.test"/)
  assert.match(prompt, /\/downloads\/ACP_AGENT\.zip/)
  assert.match(prompt, /--stop-after-message --timeout-seconds 300/)
})
