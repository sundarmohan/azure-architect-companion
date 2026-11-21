import { describe, expect, it } from 'vitest'
import { toCanvas } from './canvasMapper'
import { active, architecture, catalogMap, group, snapshot, vm } from '../test/fixtures'

describe('canvasMapper', () => {
  it('renders a resource node', () => expect(toCanvas(snapshot, {}, catalogMap).nodes.find((node) => node.id === vm.id)?.type).toBe('resource'))
  it('renders a catalog-declared container', () => expect(toCanvas(snapshot, {}, catalogMap).nodes.find((node) => node.id === group.id)?.type).toBe('container'))
  it('preserves hierarchy through parentId', () => expect(toCanvas(snapshot, {}, catalogMap).nodes.find((node) => node.id === vm.id)?.parentId).toBe(group.id))
  it('renders independent root containers', () => {
    const second = { ...group, id: 'r3', resource_key: 'second', name: 'second' }
    const nodes = toCanvas({ ...snapshot, resources: [...snapshot.resources, second] }, {}, catalogMap).nodes
    expect(nodes.filter((node) => !node.parentId)).toHaveLength(2)
  })
  it('renders logical relationships', () => expect(toCanvas(snapshot, {}, catalogMap).edges.some((edge) => edge.id === 'relationship:rel1')).toBe(true))
  it('renders technical dependencies separately', () => expect(toCanvas(snapshot, {}, catalogMap).edges.find((edge) => edge.id === 'dependency:dep1')?.data?.kind).toBe('dependency'))
  it('uses stored layout coordinates', () => expect(toCanvas(snapshot, { r2: { position: { x: 44, y: 55 } } }, catalogMap).nodes.find((node) => node.id === 'r2')?.position).toEqual({ x: 44, y: 55 }))
  it('marks immutable versions read-only', () => {
    const result = toCanvas({ ...snapshot, architecture, version: active }, {}, catalogMap)
    expect(result.nodes.every((node) => node.draggable === false)).toBe(true)
  })
  it('renders unknown catalog resources gracefully', () => {
    const unknown = { ...vm, id: 'unknown', resource_type: 'catalog/future' }
    expect(toCanvas({ ...snapshot, resources: [unknown], relationships: [], dependencies: [] }, {}, catalogMap).nodes[0].type).toBe('resource')
  })
})
