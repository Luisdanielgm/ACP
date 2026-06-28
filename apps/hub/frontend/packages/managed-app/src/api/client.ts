const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export function apiUrl(path: string): string {
  return `${BASE_URL}${path}`
}

export class ApiError extends Error {
  status: number
  body?: any
  constructor(response: Response, body?: any) {
    super(body?.message || body?.detail || `API error: ${response.status}`)
    this.status = response.status
    this.body = body
  }
}

export function getApiErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    return err.body?.detail || err.body?.message || err.message
  }
  if (err instanceof Error) return err.message
  return String(err)
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    credentials: 'include',
    ...options,
  })
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response, body)
  return body as T
}
