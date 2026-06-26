export interface ManagedSessionDashboardTarget {
  sessionId: string
  agentName?: string | null
  memberToken?: string | null
}

/**
 * Build the URL the managed SPA opens to enter the per-session live view.
 *
 * session_id and agent_name are placed in the query string. member_token is
 * placed in the URL fragment (hash) so it never appears in proxy access logs,
 * Referer headers, or server-side browser history backends. The SPA reads
 * location.hash to recover it; see readManagedSessionMemberTokenFromHash().
 */
export function buildManagedSessionDashboardPath(target: ManagedSessionDashboardTarget): string {
  const query = new URLSearchParams()
  query.set('session_id', target.sessionId)

  const agentName = String(target.agentName || '').trim()
  const memberToken = String(target.memberToken || '').trim()
  if (agentName) {
    query.set('agent_name', agentName)
  }

  const base = `/managed/dashboard/session?${query.toString()}`
  if (agentName && memberToken) {
    const fragment = new URLSearchParams()
    fragment.set('member_token', memberToken)
    return `${base}#${fragment.toString()}`
  }
  return base
}

/**
 * Read a member_token that was passed via the URL fragment.
 *
 * Falls back to reading from the query string for backwards compatibility
 * with previously issued share URLs. After reading, callers should call
 * scrubManagedSessionMemberTokenFromHash() to remove the token from the
 * visible address bar.
 */
export function readManagedSessionMemberTokenFromLocation(loc: Location | { hash: string; search: string }): string | null {
  const hash = String(loc.hash || '').replace(/^#/, '')
  if (hash) {
    const fragment = new URLSearchParams(hash)
    const token = fragment.get('member_token')
    if (token && token.trim()) {
      return token.trim()
    }
  }
  const search = String(loc.search || '').replace(/^\?/, '')
  if (search) {
    const query = new URLSearchParams(search)
    const token = query.get('member_token')
    if (token && token.trim()) {
      return token.trim()
    }
  }
  return null
}

/** Remove member_token from window.location.hash without reloading. */
export function scrubManagedSessionMemberTokenFromHash(): void {
  if (typeof window === 'undefined' || !window.history?.replaceState) {
    return
  }
  const hash = String(window.location.hash || '').replace(/^#/, '')
  if (!hash) {
    return
  }
  const fragment = new URLSearchParams(hash)
  if (!fragment.has('member_token')) {
    return
  }
  fragment.delete('member_token')
  const remaining = fragment.toString()
  const newUrl = window.location.pathname + window.location.search + (remaining ? `#${remaining}` : '')
  window.history.replaceState(window.history.state, '', newUrl)
}
