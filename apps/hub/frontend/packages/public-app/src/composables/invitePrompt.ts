export interface InvitePromptPayload {
  session_id?: string
  join_code?: string
  hub_http?: string
  official_hub_http?: string
  hub_ws?: string
}

const MINIMUM_CLIENT_VERSION = '0.3.15'

function normalizedHttpOrigin(value: string | undefined): string {
  const candidate = String(value || '').trim()
  if (!candidate) return ''
  try {
    const parsed = new URL(candidate)
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return ''
    return parsed.origin
  } catch {
    return ''
  }
}

export function hubOriginForInvite(payload: InvitePromptPayload, pageOrigin = ''): string {
  return normalizedHttpOrigin(pageOrigin)
    || normalizedHttpOrigin(payload.hub_http)
    || normalizedHttpOrigin(payload.official_hub_http)
}

export function hubWsForInvite(payload: InvitePromptPayload, pageOrigin = ''): string {
  const explicitWs = String(payload.hub_ws || '').trim()
  if (/^wss?:\/\//i.test(explicitWs)) return explicitWs
  const http = hubOriginForInvite(payload, pageOrigin)
  if (!http) return ''
  return http.replace(/^http/, 'ws') + '/ws'
}

export function buildInvitePrompt(payload: InvitePromptPayload, lang = 'en', pageOrigin = ''): string {
  const origin = hubOriginForInvite(payload, pageOrigin)
  if (!origin) throw new Error('Hub HTTP origin is required to build an ACP invitation.')

  const sid = String(payload.session_id || '').trim()
  const join = String(payload.join_code || '').trim() || '<JOIN_CODE>'
  const es = lang === 'es'
  const lines: string[] = []

  if (es) {
    lines.push(`# Requisito: Python 3 y cliente ACP ${MINIMUM_CLIENT_VERSION} o posterior.`)
    lines.push('# Si ACP_AGENT/acp.py no existe, descarga y extrae el bundle oficial en la raiz del proyecto:')
  } else {
    lines.push(`# Requirement: Python 3 and ACP client ${MINIMUM_CLIENT_VERSION} or newer.`)
    lines.push('# If ACP_AGENT/acp.py does not exist, download and extract the official bundle in the project root:')
  }
  lines.push(`curl --fail --location "${origin}/downloads/ACP_AGENT.zip" --output ACP_AGENT.zip`)
  lines.push('python -m zipfile -e ACP_AGENT.zip ACP_AGENT')
  lines.push('')

  lines.push(es ? '# Comprueba la version y actualiza solo cuando el cliente este inactivo:' : '# Check the version and update only while the client is idle:')
  lines.push('python ACP_AGENT/acp.py --version')
  lines.push(`python ACP_AGENT/acp.py update-check --hub-http "${origin}"`)
  lines.push(`python ACP_AGENT/acp.py self-update --hub-http "${origin}" --auto-when-idle`)
  lines.push('')

  lines.push(es ? '# Elige UN modo. Usa una identidad/config distinta por agente; nunca reutilices el config del chief.' : '# Choose ONE mode. Use a distinct identity/config per agent; never reuse the chief config.')
  lines.push('')
  lines.push(es ? '# Modo por turnos: une al agente (crea el config si no existe) y recibe un solo mensaje por ciclo.' : '# Turn-based mode: join the agent (creates the config when missing) and receive one message per cycle.')
  lines.push('python ACP_AGENT/acp.py join-session \\')
  lines.push('  --config ACP_AGENT/agents/<agent>.json \\')
  lines.push('  --agent <agent> \\')
  lines.push(`  --hub-http "${origin}" \\`)
  lines.push(`  --code "${join}"`)
  lines.push('python ACP_AGENT/acp.py listen --agent <agent> --stop-after-message --timeout-seconds 300')
  lines.push('')

  lines.push(es ? '# Modo siempre activo: NO ejecutes el join anterior; el runner se une y despierta al proveedor local.' : '# Always-on mode: do NOT run the join above; the runner joins and wakes the local provider.')
  lines.push('python ACP_AGENT/acp.py runner start \\')
  lines.push('  --config ACP_AGENT/agents/<agent>.json \\')
  lines.push('  --agent <agent> \\')
  lines.push(`  --hub-http "${origin}" \\`)
  lines.push(`  --join-code "${join}" \\`)
  lines.push('  --provider <codex_local|claude_local> \\')
  lines.push('  --workspace "<ABSOLUTE_PROJECT_PATH>" \\')
  lines.push('  --allow-sender "<TRUSTED_COORDINATOR>" \\')
  lines.push('  --reply-to "<TRUSTED_COORDINATOR>"')
  lines.push('')

  lines.push(es ? '# No uses listen persistente en primer plano para un LLM. No compartas tokens generados ni otros configs.' : '# Do not use persistent foreground listen for an LLM. Do not share generated tokens or other configs.')
  if (!payload.join_code && sid) lines.push(`# Session ID: ${sid}`)
  return lines.join('\n')
}
