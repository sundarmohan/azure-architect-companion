import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { ResourceIcon } from './ResourceIcon'
import type { ResourceNodeData } from '../../services/canvasMapper'

export const ResourceNode = memo(function ResourceNode({ data, selected }: NodeProps) {
  const nodeData = data as ResourceNodeData
  const { resource, readOnly } = nodeData
  return (
    <article className={`resource-node${selected ? ' is-selected' : ''}`} aria-label={`${resource.name} resource`}>
      <Handle type="target" position={Position.Left} />
      <div className="resource-node__icon"><ResourceIcon /></div>
      <div className="resource-node__copy">
        <strong>{resource.name}</strong>
        <span>{resource.resource_type.split('/').at(-1) ?? resource.resource_type}</span>
      </div>
      <span className={`resource-node__state ${readOnly ? 'is-locked' : ''}`} title={readOnly ? 'Read-only version' : 'Editable draft'} />
      <Handle type="source" position={Position.Right} />
    </article>
  )
})
