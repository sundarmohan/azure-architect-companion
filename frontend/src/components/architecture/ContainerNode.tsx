import { memo } from 'react'
import { Handle, NodeResizer, Position, type NodeProps } from '@xyflow/react'
import { Box } from 'lucide-react'
import type { ResourceNodeData } from '../../services/canvasMapper'

export const ContainerNode = memo(function ContainerNode({ data, selected }: NodeProps) {
  const nodeData = data as ResourceNodeData
  const { resource, readOnly } = nodeData
  return (
    <section className={`container-node${selected ? ' is-selected' : ''}`} aria-label={`${resource.name} container`}>
      <NodeResizer isVisible={selected && !readOnly} minWidth={280} minHeight={180} lineClassName="resize-line" handleClassName="resize-handle" />
      <header className="container-node__header">
        <Box size={17} aria-hidden="true" />
        <strong>{resource.name}</strong>
        <span>{resource.resource_type.split('/').at(-1)}</span>
      </header>
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
    </section>
  )
})
