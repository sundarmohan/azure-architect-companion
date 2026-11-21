import type { Edge, Node, XYPosition } from '@xyflow/react'
import type { ArchitectureSnapshot, Resource } from '../models/architecture'
import type { CatalogResourceDetail } from '../models/catalog'
import type { LayoutEntry } from './layoutStore'

export interface ResourceNodeData extends Record<string, unknown> {
  resource: Resource
  container: boolean
  readOnly: boolean
}

const defaultPosition = (index: number): XYPosition => ({ x: 80 + (index % 4) * 220, y: 80 + Math.floor(index / 4) * 150 })

export function toCanvas(snapshot: ArchitectureSnapshot, layout: Record<string, LayoutEntry>, catalog: Record<string, CatalogResourceDetail>): { nodes: Node<ResourceNodeData>[]; edges: Edge[] } {
  const resourceById = new Map(snapshot.resources.map((resource) => [resource.id, resource]))
  const readOnly = snapshot.version.status.toUpperCase() !== 'DRAFT'
  const nodes = snapshot.resources.map((resource, index): Node<ResourceNodeData> => {
    const container = snapshot.resources.some((candidate) => candidate.parent_resource_id === resource.id) || (catalog[resource.resource_type]?.valid_child_types.length ?? 0) > 0
    return {
      id: resource.id,
      type: container ? 'container' : 'resource',
      parentId: resource.parent_resource_id ?? undefined,
      extent: resource.parent_resource_id ? 'parent' : undefined,
      position: layout[resource.id]?.position ?? defaultPosition(index),
      style: container ? { width: Math.max(layout[resource.id]?.width ?? 360, 280), height: Math.max(layout[resource.id]?.height ?? 220, 180) } : undefined,
      data: { resource, container, readOnly },
      draggable: !readOnly,
      selectable: true,
    }
  })
  const relationshipEdges = snapshot.relationships.map((relationship): Edge => ({
    id: `relationship:${relationship.id}`,
    source: relationship.source_resource_id,
    target: relationship.target_resource_id,
    type: 'relationship',
    label: relationship.relationship_type,
    data: { kind: 'relationship' },
  }))
  const dependencyEdges = snapshot.dependencies.map((dependency): Edge => ({
    id: `dependency:${dependency.id}`,
    source: dependency.resource_id,
    target: dependency.depends_on_resource_id,
    type: 'relationship',
    label: dependency.dependency_type,
    data: { kind: 'dependency', required: dependency.required },
  }))
  return { nodes, edges: [...relationshipEdges, ...dependencyEdges] }
}
