import { useState } from 'react'
import { X } from 'lucide-react'

interface TextEntryDialogProps {
  title: string
  label: string
  submitLabel: string
  placeholder?: string
  onCancel: () => void
  onSubmit: (value: string) => void
}

export function TextEntryDialog({ title, label, submitLabel, placeholder, onCancel, onSubmit }: TextEntryDialogProps) {
  const [value, setValue] = useState('')
  return <div className="modal-backdrop" role="presentation"><form className="text-entry-dialog" role="dialog" aria-modal="true" aria-label={title} onSubmit={(event) => { event.preventDefault(); if (value.trim()) onSubmit(value.trim()) }}><header><h2>{title}</h2><button type="button" className="icon-button" onClick={onCancel} title="Close"><X size={18} /></button></header><label>{label}<input autoFocus value={value} placeholder={placeholder} onChange={(event) => setValue(event.target.value)} /></label><div className="form-actions"><button type="button" className="secondary-button" onClick={onCancel}>Cancel</button><button type="submit" className="primary-button" disabled={!value.trim()}>{submitLabel}</button></div></form></div>
}
