import { useDeferredValue, useState } from 'react'
import { Search } from 'lucide-react'
import type { CatalogResource } from '../../models/catalog'
import { ResourceIcon } from './ResourceIcon'

interface ResourceCatalogProps {
  resources: CatalogResource[]
  loading: boolean
  disabled: boolean
}

export function ResourceCatalog({ resources, loading, disabled }: ResourceCatalogProps) {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('All')
  const deferredSearch = useDeferredValue(search.toLowerCase())
  const categories = ['All', ...Array.from(new Set(resources.map((item) => item.category))).sort()]
  const filtered = resources.filter((item) =>
    (category === 'All' || item.category === category) &&
    (`${item.display_name} ${item.resource_type}`.toLowerCase().includes(deferredSearch))
  )

  return (
    <aside className="catalog-panel" aria-label="Resource catalog">
      <div className="panel-heading"><span>Resource catalog</span><small>{resources.length} types</small></div>
      <label className="search-field"><Search size={16} /><span className="sr-only">Search resources</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search resources" /></label>
      <div className="category-tabs" role="tablist" aria-label="Catalog categories">
        {categories.map((item) => <button key={item} role="tab" aria-selected={category === item} onClick={() => setCategory(item)}>{item}</button>)}
      </div>
      <div className="catalog-list">
        {loading && <p className="panel-message">Loading catalog...</p>}
        {!loading && filtered.map((item) => (
          <button
            className="catalog-item"
            key={item.id}
            draggable={!disabled}
            disabled={disabled}
            onDragStart={(event) => {
              event.dataTransfer.setData('application/aac-catalog-resource', JSON.stringify({ resourceType: item.resource_type }))
              event.dataTransfer.effectAllowed = 'copy'
            }}
            title={disabled ? 'Create or select a draft to add resources' : `Drag ${item.display_name} to the canvas`}
          >
            <span className="catalog-item__icon"><ResourceIcon category={item.category} /></span>
            <span><strong>{item.display_name}</strong><small>{item.category}</small></span>
          </button>
        ))}
        {!loading && filtered.length === 0 && <p className="panel-message">No catalog resources match.</p>}
      </div>
    </aside>
  )
}
