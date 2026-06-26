const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export class ApiError extends Error {
  status: number
  body?: any
  constructor(response: Response, body?: any) {
    super(body?.message || body?.detail || `API error: ${response.status} ${response.statusText}`)
    this.status = response.status
    this.body = body
  }
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    credentials: 'include',
    ...options,
  })
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response, body)
  return body as T
}
