import { GitCompareArrows, Plus, Redo2, Undo2 } from 'lucide-react'
import type { Architecture, ArchitectureVersion } from '../../models/architecture'
import { SaveStatus, type SaveState } from './SaveStatus'

interface ArchitectureHeaderProps {
  architectures: Architecture[]
  versions: ArchitectureVersion[]
  architectureId: string
  versionId: string
  saveState: SaveState
  onArchitectureChange: (id: string) => void
  onVersionChange: (id: string) => void
  onCreateVersion: () => void
  onCompare: () => void
  onUndo: () => void
  onRedo: () => void
  canUndo: boolean
  canRedo: boolean
}

export function ArchitectureHeader(props: ArchitectureHeaderProps) {
  const current = props.versions.find((item) => item.id === props.versionId)
  return <header className="architecture-header">
    <div className="brand"><span className="brand-mark">AA</span><div><strong>Azure Architect</strong><small>Companion</small></div></div>
    <div className="architecture-selectors">
      <label>Architecture<select value={props.architectureId} onChange={(event) => props.onArchitectureChange(event.target.value)}>{props.architectures.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label>Version<select value={props.versionId} onChange={(event) => props.onVersionChange(event.target.value)}>{props.versions.map((item) => <option key={item.id} value={item.id}>V{item.version_sequence ?? item.version_number} · {item.status.toUpperCase()}</option>)}</select></label>
      {current && <span className={`status-badge status-badge--${current.status.toLowerCase()}`}>{current.status.toUpperCase()}</span>}
    </div>
    <div className="header-actions">
      <button className="icon-button" onClick={props.onUndo} disabled={!props.canUndo} title="Undo canvas change"><Undo2 size={18} /></button>
      <button className="icon-button" onClick={props.onRedo} disabled={!props.canRedo} title="Redo canvas change"><Redo2 size={18} /></button>
      <SaveStatus state={props.saveState} />
      <button className="secondary-button" onClick={props.onCompare}><GitCompareArrows size={16} />Compare</button>
      <button className="primary-button" onClick={props.onCreateVersion}><Plus size={16} />New version</button>
    </div>
  </header>
}
