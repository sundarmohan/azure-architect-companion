import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, request } from './apiClient'

afterEach(() => vi.unstubAllGlobals())

describe('apiClient', () => {
  it('returns typed JSON for successful requests', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'a1' }), { status: 200 })))
    await expect(request<{ id: string }>('/architectures/a1')).resolves.toEqual({ id: 'a1' })
  })
  it('maps structured API errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { code: 'VERSION_IMMUTABLE', message: 'Version is immutable' } }), { status: 409 })))
    await expect(request('/resource')).rejects.toMatchObject({ code: 'VERSION_IMMUTABLE', status: 409 })
  })
  it('maps network failures without leaking details', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('client_secret=unsafe')))
    await expect(request('/resource')).rejects.toMatchObject({ code: 'NETWORK_ERROR', message: 'Cannot reach the architecture service.' })
  })
  it('sanitizes secret-bearing error labels', () => expect(new ApiError(400, { code: 'BAD', message: 'password was rejected' }).message).not.toContain('password'))
  it('supports empty delete responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    await expect(request('/resource', { method: 'DELETE' })).resolves.toBeUndefined()
  })
})
