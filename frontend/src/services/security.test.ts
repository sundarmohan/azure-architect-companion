import { describe, expect, it } from 'vitest'
import { containsSensitiveKey, stripSensitive } from './security'

describe('frontend secret handling', () => {
  it('removes nested secret-bearing fields before retaining UI state', () => {
    expect(stripSensitive({ nested: { client_secret: 'hidden', enabled: true } })).toEqual({ nested: { enabled: true } })
  })
  it('detects secret-bearing edits before persistence', () => {
    expect(containsSensitiveKey({ tags: { api_key: 'hidden' } })).toBe(true)
  })
  it('preserves non-sensitive configuration', () => {
    expect(stripSensitive({ location: 'eastus', sku: { name: 'small' } })).toEqual({ location: 'eastus', sku: { name: 'small' } })
  })
})
