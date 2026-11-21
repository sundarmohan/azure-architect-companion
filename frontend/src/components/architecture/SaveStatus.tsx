import { AlertCircle, Check, LoaderCircle } from 'lucide-react'

export type SaveState = 'saved' | 'saving' | 'unsaved' | 'failed'

export function SaveStatus({ state }: { state: SaveState }) {
  const labels: Record<SaveState, string> = { saved: 'Saved', saving: 'Saving...', unsaved: 'Unsaved changes', failed: 'Save failed' }
  const Icon = state === 'saved' ? Check : state === 'saving' ? LoaderCircle : AlertCircle
  return <span className={`save-status save-status--${state}`} role="status"><Icon size={14} className={state === 'saving' ? 'spin' : ''} />{labels[state]}</span>
}
