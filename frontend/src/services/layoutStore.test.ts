import { beforeEach, describe, expect, it } from 'vitest'
import { loadLayout, replaceLayoutKey, setLayoutEntry } from './layoutStore'

beforeEach(() => localStorage.clear())

describe('layoutStore', () => {
  it('persists presentation coordinates without canonical data', () => {
    setLayoutEntry('v1', 'r1', { position: { x: 10, y: 20 } })
    expect(loadLayout('v1').r1.position).toEqual({ x: 10, y: 20 })
    expect(localStorage.getItem('aac:layout:v1')).not.toContain('properties')
  })
  it('moves staged layout to the backend resource identity', () => {
    setLayoutEntry('v1', 'draft:1', { position: { x: 1, y: 2 } })
    replaceLayoutKey('v1', 'draft:1', 'resource-1')
    expect(loadLayout('v1')['draft:1']).toBeUndefined()
    expect(loadLayout('v1')['resource-1'].position.x).toBe(1)
  })
})
