import { AlertTriangle } from 'lucide-react'
import type { Resource } from '../../models/architecture'

export function DeleteConfirmation({ resource, affected, onCancel, onConfirm }: { resource: Resource; affected: Resource[]; onCancel: () => void; onConfirm: () => void }) {
  return <div className="modal-backdrop" role="presentation"><section className="confirm-dialog" role="alertdialog" aria-modal="true" aria-label="Confirm resource deletion"><AlertTriangle size={28} /><h2>Delete {resource.name}?</h2><p>This action updates the backend draft. Relationships and dependencies must be removed first.</p>{affected.length > 0 && <div><strong>Affected child resources</strong><ul>{affected.map((item) => <li key={item.id}>{item.name}</li>)}</ul></div>}<div className="form-actions"><button className="secondary-button" onClick={onCancel}>Cancel</button><button className="danger-button" onClick={onConfirm}>Delete resource</button></div></section></div>
}
