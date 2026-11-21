import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  applyNodeChanges,
  type Connection,
  type Node,
  type NodeChange,
  type OnSelectionChangeParams,
  type ReactFlowInstance,
  type XYPosition,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Boxes } from 'lucide-react'
import type { ArchitectureSnapshot } from '../../models/architecture'
import type { CatalogResourceDetail } from '../../models/catalog'
import { loadLayout, saveLayout } from '../../services/layoutStore'
import { toCanvas, type ResourceNodeData } from '../../services/canvasMapper'
import { ContainerNode } from './ContainerNode'
import { RelationshipEdge } from './RelationshipEdge'
import { ResourceNode } from './ResourceNode'
import type { SaveState } from './SaveStatus'

const nodeTypes = { resource: ResourceNode, container: ContainerNode }
const edgeTypes = { relationship: RelationshipEdge }

export interface CanvasHandle {
  undo: () => void
  redo: () => void
}

interface ArchitectureCanvasProps {
  snapshot: ArchitectureSnapshot
  catalog: Record<string, CatalogResourceDetail>
  onSelect: (resourceId: string | null) => void
  onDropResource: (resourceType: string, position: XYPosition, parentId: string | null) => Promise<void>
  onConnect: (connection: Connection) => void
  onSaveState: (state: SaveState) => void
  onHistoryState: (canUndo: boolean, canRedo: boolean) => void
  rootContainer: CatalogResourceDetail | null
  onBrowseCatalog: () => void
}

export const ArchitectureCanvas = forwardRef<CanvasHandle, ArchitectureCanvasProps>(function ArchitectureCanvas({ snapshot, catalog, onSelect, onDropResource, onConnect, onSaveState, onHistoryState, rootContainer, onBrowseCatalog }, ref) {
  const initial = toCanvas(snapshot, loadLayout(snapshot.version.id), catalog)
  const [nodes, setNodes] = useState<Node<ResourceNodeData>[]>(initial.nodes)
  const [edges, setEdges] = useState(initial.edges)
  const [error, setError] = useState<string | null>(null)
  const history = useRef<Node<ResourceNodeData>[][]>([initial.nodes])
  const historyIndex = useRef(0)
  const wrapper = useRef<HTMLDivElement>(null)
  const flow = useRef<ReactFlowInstance<Node<ResourceNodeData>> | null>(null)

  useEffect(() => {
    const mapped = toCanvas(snapshot, loadLayout(snapshot.version.id), catalog)
    setNodes(mapped.nodes)
    setEdges(mapped.edges)
    history.current = [mapped.nodes]
    historyIndex.current = 0
    onHistoryState(false, false)
  }, [snapshot, catalog, onHistoryState])

  function record(next: Node<ResourceNodeData>[]) {
    history.current = [...history.current.slice(0, historyIndex.current + 1), next]
    historyIndex.current += 1
    onHistoryState(historyIndex.current > 0, false)
  }

  useImperativeHandle(ref, () => ({
    undo() {
      if (historyIndex.current === 0) return
      historyIndex.current -= 1
      setNodes(history.current[historyIndex.current])
      persist(history.current[historyIndex.current])
      onHistoryState(historyIndex.current > 0, true)
    },
    redo() {
      if (historyIndex.current >= history.current.length - 1) return
      historyIndex.current += 1
      setNodes(history.current[historyIndex.current])
      persist(history.current[historyIndex.current])
      onHistoryState(true, historyIndex.current < history.current.length - 1)
    },
  }))

  function persist(next: Node<ResourceNodeData>[]) {
    onSaveState('saving')
    try {
      saveLayout(snapshot.version.id, next)
      onSaveState('saved')
    } catch {
      onSaveState('failed')
    }
  }

  function handleNodesChange(changes: NodeChange<Node<ResourceNodeData>>[]) {
    setNodes((current) => {
      const next = applyNodeChanges(changes, current)
      if (changes.some((change) => change.type === 'dimensions' && !change.resizing)) {
        const expanded = expandContainers(next)
        record(expanded)
        persist(expanded)
        return expanded
      }
      return next
    })
    if (changes.some((change) => change.type === 'position' || change.type === 'dimensions')) onSaveState('unsaved')
  }

  function handleDragStop() {
    setNodes((current) => {
      const expanded = expandContainers(current)
      record(expanded)
      persist(expanded)
      return expanded
    })
  }

  function absolutePosition(node: Node<ResourceNodeData>, all: Node<ResourceNodeData>[]): XYPosition {
    if (!node.parentId) return node.position
    const parent = all.find((item) => item.id === node.parentId)
    if (!parent) return node.position
    const parentPosition = absolutePosition(parent, all)
    return { x: parentPosition.x + node.position.x, y: parentPosition.y + node.position.y }
  }

  function findParent(point: XYPosition): string | null {
    return nodes
      .filter((node) => node.data.container)
      .map((node) => ({ node, absolute: absolutePosition(node, nodes), width: node.measured?.width ?? Number(node.style?.width ?? 360), height: node.measured?.height ?? Number(node.style?.height ?? 220) }))
      .filter(({ absolute, width, height }) => point.x >= absolute.x && point.x <= absolute.x + width && point.y >= absolute.y && point.y <= absolute.y + height)
      .sort((left, right) => left.width * left.height - right.width * right.height)[0]?.node.id ?? null
  }

  async function handleDrop(event: React.DragEvent) {
    event.preventDefault()
    const raw = event.dataTransfer.getData('application/aac-catalog-resource')
    if (!raw || !flow.current) return
    try {
      const payload = JSON.parse(raw) as { resourceType?: string }
      if (!payload.resourceType) return
      const point = flow.current.screenToFlowPosition({ x: event.clientX, y: event.clientY })
      const parentId = findParent(point)
      const parent = nodes.find((node) => node.id === parentId)
      const parentPosition = parent ? absolutePosition(parent, nodes) : null
      const localPoint = parentPosition ? { x: point.x - parentPosition.x - 20, y: point.y - parentPosition.y - 48 } : point
      await onDropResource(payload.resourceType, localPoint, parentId)
      setError(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The resource could not be added.')
    }
  }

  function handleConnect(connection: Connection) {
    onConnect(connection)
    setError(null)
  }

  const empty = snapshot.resources.length === 0
  return <main className="canvas-shell" ref={wrapper} onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = 'copy' }} onDrop={handleDrop}>
    {error && <div className="canvas-alert" role="alert">{error}</div>}
    {empty && <div className="canvas-empty"><Boxes size={34} /><strong>Start designing your Azure architecture</strong><p>Drag a resource from the catalog onto this canvas.</p><div className="empty-actions">{rootContainer && snapshot.version.status.toUpperCase() === 'DRAFT' && <button className="primary-button" onClick={() => void onDropResource(rootContainer.resource_type, { x: 80, y: 80 }, null)}>Add {rootContainer.display_name}</button>}<button className="secondary-button" onClick={onBrowseCatalog}>Browse resource catalog</button></div></div>}
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onInit={(instance) => { flow.current = instance }}
      onNodesChange={handleNodesChange}
      onNodeDragStop={handleDragStop}
      onConnect={handleConnect}
      onSelectionChange={(selection: OnSelectionChangeParams) => onSelect(selection.nodes[0]?.id ?? null)}
      nodesConnectable={snapshot.version.status.toUpperCase() === 'DRAFT'}
      fitView
      minZoom={0.2}
      maxZoom={1.8}
      defaultEdgeOptions={{ markerEnd: { type: MarkerType.ArrowClosed }, selectable: true }}
      deleteKeyCode={null}
    >
      <Background gap={24} size={1} color="#c8d2dc" />
      <Controls showInteractive={false} />
    </ReactFlow>
  </main>
})

function expandContainers(nodes: Node<ResourceNodeData>[]): Node<ResourceNodeData>[] {
  const padding = 52
  const next = nodes.map((node) => ({ ...node, style: node.style ? { ...node.style } : undefined }))
  for (const parent of [...next].reverse()) {
    if (!parent.data.container) continue
    const children = next.filter((node) => node.parentId === parent.id)
    if (children.length === 0) continue
    const requiredWidth = Math.max(...children.map((node) => node.position.x + (node.measured?.width ?? 180))) + padding
    const requiredHeight = Math.max(...children.map((node) => node.position.y + (node.measured?.height ?? 72))) + padding
    parent.style = { ...parent.style, width: Math.max(Number(parent.style?.width ?? 280), requiredWidth), height: Math.max(Number(parent.style?.height ?? 180), requiredHeight) }
  }
  return next
}
