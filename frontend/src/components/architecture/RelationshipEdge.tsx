import { BaseEdge, EdgeLabelRenderer, getBezierPath, type EdgeProps } from '@xyflow/react'

export function RelationshipEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, label, data, markerEnd }: EdgeProps) {
  const [path, labelX, labelY] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition })
  const dependency = data?.kind === 'dependency'
  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={markerEnd} className={dependency ? 'edge edge--dependency' : 'edge edge--relationship'} />
      <EdgeLabelRenderer>
        <span className={`edge-label ${dependency ? 'edge-label--dependency' : ''}`} style={{ transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)` }}>
          {String(label ?? '')}
        </span>
      </EdgeLabelRenderer>
    </>
  )
}
