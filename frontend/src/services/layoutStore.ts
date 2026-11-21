import type { Node, XYPosition } from '@xyflow/react'

export interface LayoutEntry {
  position: XYPosition
  width?: number
  height?: number
}

const keyFor = (versionId: string) => `aac:layout:${versionId}`

export function loadLayout(versionId: string): Record<string, LayoutEntry> {
  try {
    const raw = window.localStorage.getItem(keyFor(versionId))
    return raw ? (JSON.parse(raw) as Record<string, LayoutEntry>) : {}
  } catch {
    return {}
  }
}

export function saveLayout(versionId: string, nodes: Node[]): void {
  const layout = Object.fromEntries(nodes.map((node) => [node.id, {
    position: node.position,
    width: node.measured?.width,
    height: node.measured?.height,
  }]))
  window.localStorage.setItem(keyFor(versionId), JSON.stringify(layout))
}

export function setLayoutEntry(versionId: string, resourceId: string, entry: LayoutEntry): void {
  const layout = loadLayout(versionId)
  window.localStorage.setItem(keyFor(versionId), JSON.stringify({ ...layout, [resourceId]: entry }))
}

export function replaceLayoutKey(versionId: string, fromId: string, toId: string): void {
  const layout = loadLayout(versionId)
  const entry = layout[fromId]
  if (!entry) return
  delete layout[fromId]
  layout[toId] = entry
  window.localStorage.setItem(keyFor(versionId), JSON.stringify(layout))
}
