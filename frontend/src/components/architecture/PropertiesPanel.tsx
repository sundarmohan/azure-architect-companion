import { useEffect, useState } from 'react'
import { Save, Trash2, X } from 'lucide-react'
import type { Resource, ResourceUpdate } from '../../models/architecture'
import type { CatalogResourceDetail, JsonSchemaProperty } from '../../models/catalog'

const sensitive = /(password|secret|token|api[_-]?key|private[_-]?key|connection[_-]?string)/i

interface PropertiesPanelProps {
  resource: Resource | null
  catalog: CatalogResourceDetail | null
  readOnly: boolean
  relationshipCount: number
  onSave: (update: ResourceUpdate) => Promise<void>
  onDelete: () => void
  onClose: () => void
}

export function PropertiesPanel({ resource, catalog, readOnly, relationshipCount, onSave, onDelete, onClose }: PropertiesPanelProps) {
  const [name, setName] = useState('')
  const [location, setLocation] = useState('')
  const [sku, setSku] = useState('{}')
  const [properties, setProperties] = useState<Record<string, unknown>>({})
  const [tags, setTags] = useState('{}')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setName(resource?.name ?? '')
    setLocation(resource?.location ?? '')
    setSku(JSON.stringify(resource?.sku ?? {}, null, 2))
    setProperties(resource?.properties ?? {})
    setTags(JSON.stringify(resource?.tags ?? {}, null, 2))
    setError(null)
  }, [resource])

  if (!resource) return <aside className="properties-panel"><div className="panel-heading"><span>Properties</span></div><p className="panel-message">Select a resource to inspect its configuration.</p></aside>

  const schemaProperties = Object.entries(catalog?.properties_schema?.properties ?? {}).filter(([key]) => !sensitive.test(key))

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    try {
      setError(null)
      await onSave({ name, location: location || null, sku: JSON.parse(sku) as Record<string, unknown>, properties, tags: JSON.parse(tags) as Record<string, string> })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The resource could not be saved.')
    }
  }

  function updateProperty(key: string, definition: JsonSchemaProperty, raw: string | boolean) {
    let value: unknown = raw
    if (definition.type === 'number' || definition.type === 'integer') value = Number(raw)
    setProperties((current) => ({ ...current, [key]: value }))
  }

  return (
    <aside className="properties-panel" aria-label="Resource properties">
      <div className="panel-heading"><span>Properties</span><button className="icon-button" onClick={onClose} title="Close properties"><X size={17} /></button></div>
      <form onSubmit={submit}>
        <fieldset disabled={readOnly}>
          <legend>Identity</legend>
          <label>Resource name<input value={name} required onChange={(event) => setName(event.target.value)} /></label>
          <label>Resource type<input value={resource.resource_type} disabled /></label>
          <label>Semantic key<input value={resource.resource_key} disabled /></label>
          <label>Location<input value={location} onChange={(event) => setLocation(event.target.value)} /></label>
        </fieldset>
        {schemaProperties.length > 0 && <fieldset disabled={readOnly}><legend>Configuration</legend>{schemaProperties.map(([key, definition]) => {
          const value = properties[key] ?? definition.default ?? ''
          if (definition.enum) return <label key={key}>{definition.title ?? key}<select value={String(value)} onChange={(event) => updateProperty(key, definition, event.target.value)}>{definition.enum.map((option) => <option key={String(option)} value={String(option)}>{String(option)}</option>)}</select></label>
          if (definition.type === 'boolean') return <label className="checkbox-field" key={key}><input type="checkbox" checked={Boolean(value)} onChange={(event) => updateProperty(key, definition, event.target.checked)} />{definition.title ?? key}</label>
          return <label key={key}>{definition.title ?? key}<input type={definition.type === 'number' || definition.type === 'integer' ? 'number' : 'text'} value={String(value)} onChange={(event) => updateProperty(key, definition, event.target.value)} /></label>
        })}</fieldset>}
        <fieldset disabled={readOnly}><legend>SKU</legend><label>JSON configuration<textarea value={sku} rows={4} onChange={(event) => setSku(event.target.value)} /></label></fieldset>
        <fieldset disabled={readOnly}><legend>Tags</legend><label>JSON object<textarea value={tags} rows={4} onChange={(event) => setTags(event.target.value)} /></label></fieldset>
        {catalog?.networking_requirements.length ? <Guidance title="Networking" items={catalog.networking_requirements} /> : null}
        {catalog?.security_requirements.length ? <Guidance title="Security" items={catalog.security_requirements} /> : null}
        {catalog?.monitoring_requirements.length ? <Guidance title="Monitoring" items={catalog.monitoring_requirements} /> : null}
        {catalog?.backup_requirements.length ? <Guidance title="Backup" items={catalog.backup_requirements} /> : null}
        <fieldset><legend>Relationships</legend><p className="field-note">{relationshipCount} connected relationship{relationshipCount === 1 ? '' : 's'}</p></fieldset>
        {catalog && <fieldset><legend>Catalog guidance</legend><p className="field-note">{catalog.description ?? 'No additional catalog guidance.'}</p></fieldset>}
        {error && <p className="form-error" role="alert">{error}</p>}
        {!readOnly && <div className="form-actions"><button type="button" className="danger-button" onClick={onDelete}><Trash2 size={16} />Delete</button><button type="submit" className="primary-button"><Save size={16} />Apply changes</button></div>}
      </form>
    </aside>
  )
}

function Guidance({ title, items }: { title: string; items: string[] }) {
  return <fieldset><legend>{title}</legend>{items.map((item) => <p className="field-note" key={item}>{item}</p>)}</fieldset>
}
