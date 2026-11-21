const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'
const SECRET_PATTERN = /(password|secret|token|api[_-]?key|private[_-]?key|connection[_-]?string)/gi

export interface ApiErrorBody {
  code: string
  message: string
  details?: Record<string, unknown>
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details?: Record<string, unknown>

  constructor(status: number, body: ApiErrorBody) {
    super(sanitizeMessage(body.message))
    this.name = 'ApiError'
    this.status = status
    this.code = body.code
    this.details = body.details
  }
}

function sanitizeMessage(message: string): string {
  return message.replace(SECRET_PATTERN, '[sensitive field]')
}

function normalizeError(status: number, payload: unknown): ApiErrorBody {
  if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
    const detail = (payload as { detail: unknown }).detail
    if (typeof detail === 'object' && detail !== null) {
      const value = detail as Partial<ApiErrorBody>
      return {
        code: value.code ?? `HTTP_${status}`,
        message: typeof value.message === 'string' ? value.message : 'The request could not be completed.',
        details: value.details,
      }
    }
    if (typeof detail === 'string') return { code: `HTTP_${status}`, message: detail }
  }
  return { code: `HTTP_${status}`, message: 'The request could not be completed.' }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError(0, { code: 'NETWORK_ERROR', message: 'Cannot reach the architecture service.' })
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null)
    throw new ApiError(response.status, normalizeError(response.status, payload))
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
