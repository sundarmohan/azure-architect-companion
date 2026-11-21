import { useCallback, useEffect, useRef, useState } from 'react'
import type { Connection, XYPosition } from '@xyflow/react'
import { Activity, CloudCog, GitBranch, ScanSearch, ShieldCheck } from 'lucide-react'
import { ArchitectureCanvas, type CanvasHandle } from './components/architecture/ArchitectureCanvas'
import { ArchitectureHeader } from './components/architecture/ArchitectureHeader'
import { CompliancePanel } from './components/architecture/CompliancePanel'
import { DeleteConfirmation } from './components/architecture/DeleteConfirmation'
import { DependencyPanel } from './components/architecture/DependencyPanel'
import { PropertiesPanel } from './components/architecture/PropertiesPanel'
import { ResourceCatalog } from './components/architecture/ResourceCatalog'
import type { SaveState } from './components/architecture/SaveStatus'
import { ValidationPanel } from './components/architecture/ValidationPanel'
import { VersionComparison } from './components/architecture/VersionComparison'
import { TextEntryDialog } from './components/architecture/TextEntryDialog'
import { AzurePreflightPanel } from './components/architecture/AzurePreflightPanel'
import { ConformancePanel } from './components/architecture/ConformancePanel'
import type { AzureConnectionStatus, AzurePreflightResult, AzureSnapshotSummary, ComplianceResult, ConformanceAssessment, DependencyAnalysis, DriftHistoryComparison, ValidationResult } from './models/analysis'
import type { Architecture, ArchitectureSnapshot, ArchitectureVersion, Resource, ResourceUpdate } from './models/architecture'
import type { CatalogResource, CatalogResourceDetail } from './models/catalog'
import type { VersionComparison as Comparison } from './models/versioning'
import { ApiError } from './services/apiClient'
import { architectureApi } from './services/architectureApi'
import { replaceLayoutKey, setLayoutEntry } from './services/layoutStore'
import { containsSensitiveKey, stripSensitive } from './services/security'

const emptySnapshot: ArchitectureSnapshot | null = null

type AnalysisTab = 'validation' | 'compliance' | 'dependencies' | 'azure' | 'conformance'

export default function App() {
  const [architectures, setArchitectures] = useState<Architecture[]>([])
  const [versions, setVersions] = useState<ArchitectureVersion[]>([])
  const [architectureId, setArchitectureId] = useState('')
  const [versionId, setVersionId] = useState('')
  const [snapshot, setSnapshot] = useState<ArchitectureSnapshot | null>(emptySnapshot)
  const [catalog, setCatalog] = useState<CatalogResource[]>([])
  const [catalogDetails, setCatalogDetails] = useState<Record<string, CatalogResourceDetail>>({})
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [conflict, setConflict] = useState(false)
  const [saveState, setSaveState] = useState<SaveState>('saved')
  const [analysisTab, setAnalysisTab] = useState<AnalysisTab>('validation')
  const [validation, setValidation] = useState<ValidationResult | null>(null)
  const [compliance, setCompliance] = useState<ComplianceResult | null>(null)
  const [dependencies, setDependencies] = useState<DependencyAnalysis | null>(null)
  const [azureStatus, setAzureStatus] = useState<AzureConnectionStatus | null>(null)
  const [azurePreflight, setAzurePreflight] = useState<AzurePreflightResult | null>(null)
  const [azureSnapshots, setAzureSnapshots] = useState<AzureSnapshotSummary[]>([])
  const [azureSnapshotId, setAzureSnapshotId] = useState('')
  const [conformanceHistory, setConformanceHistory] = useState<ConformanceAssessment[]>([])
  const [conformance, setConformance] = useState<ConformanceAssessment | null>(null)
  const [driftComparison, setDriftComparison] = useState<DriftHistoryComparison | null>(null)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [showCompare, setShowCompare] = useState(false)
  const [compareFrom, setCompareFrom] = useState('')
  const [compareTo, setCompareTo] = useState('')
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Resource | null>(null)
  const [canUndo, setCanUndo] = useState(false)
  const [canRedo, setCanRedo] = useState(false)
  const [showNewVersion, setShowNewVersion] = useState(false)
  const [pendingConnection, setPendingConnection] = useState<Connection | null>(null)
  const canvasRef = useRef<CanvasHandle>(null)

  useEffect(() => {
    void bootstrap()
  }, [])

  useEffect(() => {
    if (!architectureId) return
    void loadVersions(architectureId)
  }, [architectureId])

  useEffect(() => {
    const architecture = architectures.find((item) => item.id === architectureId)
    const version = versions.find((item) => item.id === versionId)
    if (!architecture || !version) return
    void loadSnapshot(architecture, version)
  }, [architectureId, versionId, architectures, versions])

  async function bootstrap() {
    setLoading(true)
    try {
      const [architectureItems, catalogResponse] = await Promise.all([
        architectureApi.listArchitectures(),
        architectureApi.listCatalog(),
      ])
      setArchitectures(architectureItems)
      setCatalog(catalogResponse.resources)
      architectureApi.getAzureStatus().then(setAzureStatus).catch(() => setAzureStatus(null))
      architectureApi.listAzureSnapshots().then((items) => { setAzureSnapshots(items); setAzureSnapshotId(items[0]?.id ?? '') }).catch(() => setAzureSnapshots([]))
      const allDetails = await Promise.all(
        catalogResponse.resources.map((item) => architectureApi.getCatalogResource(item.resource_type)),
      )
      setCatalogDetails(Object.fromEntries(allDetails.map((item) => [item.resource_type, item])))
      setArchitectureId(architectureItems[0]?.id ?? '')
      if (architectureItems.length === 0) setError('No architecture exists. Create one through the canonical architecture API first.')
    } catch (caught) {
      handleError(caught)
    } finally {
      setLoading(false)
    }
  }

  async function loadVersions(nextArchitectureId: string, preferredId?: string) {
    try {
      const items = await architectureApi.listVersions(nextArchitectureId)
      setVersions(items)
      const selected = items.find((item) => item.id === preferredId) ?? items.at(-1)
      setVersionId(selected?.id ?? '')
      setCompareFrom(items.at(-2)?.id ?? items[0]?.id ?? '')
      setCompareTo(selected?.id ?? '')
    } catch (caught) {
      handleError(caught)
    }
  }

  async function loadSnapshot(architecture: Architecture, version: ArchitectureVersion) {
    setLoading(true)
    try {
      const loaded = await architectureApi.loadSnapshot(architecture, version)
      const uniqueTypes = Array.from(new Set(loaded.resources.map((item) => item.resource_type)))
      const details = await Promise.all(uniqueTypes.map((type) => architectureApi.getCatalogResource(type)))
      setCatalogDetails((current) => ({ ...current, ...Object.fromEntries(details.map((item) => [item.resource_type, item])) }))
      setSnapshot({
        ...loaded,
        resources: loaded.resources.map((resource) => ({
          ...resource,
          properties: stripSensitive(resource.properties),
          sku: stripSensitive(resource.sku),
          tags: stripSensitive(resource.tags),
        })),
      })
      setSelectedId(null)
      setValidation(null)
      setCompliance(null)
      setDependencies(null)
      setAzurePreflight(null)
      setConformance(null)
      setDriftComparison(null)
      architectureApi.listConformance(architecture.id, version.id).then((items) => { setConformanceHistory(items); setConformance(items[0] ?? null) }).catch(() => setConformanceHistory([]))
      setPendingConnection(null)
      setConflict(false)
      setError(null)
    } catch (caught) {
      handleError(caught)
    } finally {
      setLoading(false)
    }
  }

  function handleError(caught: unknown) {
    if (caught instanceof ApiError) {
      setError(caught.message)
      if (['VERSION_STALE', 'VERSION_CONFLICT', 'VERSION_IMMUTABLE'].includes(caught.code) || caught.status === 409) setConflict(true)
    } else {
      setError(caught instanceof Error ? caught.message : 'An unexpected error occurred.')
    }
  }

  async function ensureCatalogDetail(resourceType: string) {
    const current = catalogDetails[resourceType]
    if (current) return current
    const detail = await architectureApi.getCatalogResource(resourceType)
    setCatalogDetails((items) => ({ ...items, [resourceType]: detail }))
    return detail
  }

  async function dropResource(resourceType: string, position: XYPosition, parentId: string | null) {
    if (!snapshot || snapshot.version.status.toUpperCase() !== 'DRAFT') throw new Error('Create or select a draft version before editing.')
    const detail = await ensureCatalogDetail(resourceType)
    const parent = snapshot.resources.find((item) => item.id === parentId)
    if (detail.valid_parent_types.length > 0 && (!parent || !detail.valid_parent_types.includes(parent.resource_type))) {
      throw new Error(`${detail.display_name} must be dropped inside an allowed parent container.`)
    }
    if (parent) {
      const parentDetail = await ensureCatalogDetail(parent.resource_type)
      if (!parentDetail.valid_child_types.includes(resourceType)) {
        throw new Error(`${parentDetail.display_name} cannot contain ${detail.display_name}.`)
      }
    }
    const baseKey = detail.display_name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'resource'
    const used = new Set(snapshot.resources.map((item) => item.resource_key))
    let resourceKey = baseKey
    let suffix = 2
    while (used.has(resourceKey)) resourceKey = `${baseKey}-${suffix++}`
    const temporaryId = `draft:${crypto.randomUUID()}`
    const pending: Resource = {
      id: temporaryId,
      architecture_version_id: snapshot.version.id,
      resource_key: resourceKey,
      resource_type: detail.resource_type,
      name: resourceKey,
      location: null,
      sku: null,
      properties: stripSensitive(detail.default_properties ?? {}),
      tags: {},
      parent_resource_id: parent?.id ?? null,
      created_at: '',
      updated_at: '',
    }
    setLayoutEntry(snapshot.version.id, temporaryId, { position })
    setSnapshot({ ...snapshot, resources: [...snapshot.resources, pending] })
    setSelectedId(temporaryId)
    setSaveState('unsaved')
  }

  async function saveResource(update: ResourceUpdate) {
    if (!snapshot || !selectedId) return
    const current = snapshot.resources.find((item) => item.id === selectedId)
    if (!current) return
    setSaveState('saving')
    try {
      await assertLatestDraft(snapshot.architecture.id, snapshot.version)
      if (containsSensitiveKey(update)) throw new Error('Secret-bearing fields cannot be stored by the designer.')
      let saved: Resource
      if (current.id.startsWith('draft:')) {
        saved = await architectureApi.createResource(snapshot.architecture.id, snapshot.version.id, {
          resource_key: current.resource_key,
          resource_type: current.resource_type,
          name: update.name ?? current.name,
          location: update.location,
          sku: update.sku,
          properties: update.properties,
          tags: update.tags,
          parent_resource_id: current.parent_resource_id,
        })
        replaceLayoutKey(snapshot.version.id, current.id, saved.id)
      } else {
        saved = await architectureApi.updateResource(snapshot.architecture.id, snapshot.version.id, current.id, update)
      }
      setSnapshot({ ...snapshot, resources: snapshot.resources.map((item) => item.id === current.id ? saved : item) })
      setSelectedId(saved.id)
      setSaveState('saved')
    } catch (caught) {
      setSaveState('failed')
      handleError(caught)
      throw caught
    }
  }

  async function createRelationship(connection: Connection, relationshipType: string) {
    if (!snapshot || !connection.source || !connection.target) return
    if (connection.source.startsWith('draft:') || connection.target.startsWith('draft:')) throw new Error('Save new resources before connecting them.')
    try {
      await assertLatestDraft(snapshot.architecture.id, snapshot.version)
      const relationship = await architectureApi.createRelationship(snapshot.architecture.id, snapshot.version.id, connection.source, connection.target, relationshipType)
      setSnapshot({ ...snapshot, relationships: [...snapshot.relationships, relationship] })
      const result = await architectureApi.validate(snapshot.architecture.id, snapshot.version.id)
      setValidation(result)
      setAnalysisTab('validation')
    } catch (caught) {
      handleError(caught)
      throw caught
    }
  }

  async function confirmDelete() {
    if (!snapshot || !deleteTarget) return
    const children = snapshot.resources.filter((item) => item.parent_resource_id === deleteTarget.id)
    if (children.length > 0) {
      setError('Reparent or remove child resources before deleting this container.')
      setDeleteTarget(null)
      return
    }
    try {
      await assertLatestDraft(snapshot.architecture.id, snapshot.version)
      const relationships = snapshot.relationships.filter((item) => item.source_resource_id === deleteTarget.id || item.target_resource_id === deleteTarget.id)
      const dependenciesToDelete = snapshot.dependencies.filter((item) => item.resource_id === deleteTarget.id || item.depends_on_resource_id === deleteTarget.id)
      for (const item of relationships) await architectureApi.deleteRelationship(snapshot.architecture.id, snapshot.version.id, item.id)
      for (const item of dependenciesToDelete) await architectureApi.deleteDependency(snapshot.architecture.id, snapshot.version.id, item.id)
      if (!deleteTarget.id.startsWith('draft:')) await architectureApi.deleteResource(snapshot.architecture.id, snapshot.version.id, deleteTarget.id)
      await loadSnapshot(snapshot.architecture, snapshot.version)
      setSelectedId(null)
      setDeleteTarget(null)
      setSaveState('saved')
    } catch (caught) {
      handleError(caught)
    }
  }

  async function submitNewVersion(description: string) {
    if (!snapshot) return
    try {
      const version = await architectureApi.createVersion(snapshot.architecture.id, snapshot.version.id, description)
      setShowNewVersion(false)
      await loadVersions(snapshot.architecture.id, version.id)
    } catch (caught) {
      handleError(caught)
    }
  }

  function requestRelationship(connection: Connection) {
    if (!connection.source || !connection.target) return
    setPendingConnection(connection)
  }

  async function submitRelationship(relationshipType: string) {
    if (!pendingConnection) return
    try {
      await createRelationship(pendingConnection, relationshipType)
      setPendingConnection(null)
    } catch {}
  }

  async function runAnalysis(kind: AnalysisTab, frameworks: string[] = []) {
    if (!snapshot) return
    setAnalysisLoading(true)
    try {
      if (kind === 'validation') setValidation(await architectureApi.validate(snapshot.architecture.id, snapshot.version.id))
      if (kind === 'dependencies') setDependencies(await architectureApi.analyzeDependencies(snapshot.architecture.id, snapshot.version.id))
      if (kind === 'compliance') setCompliance(await architectureApi.evaluateCompliance(snapshot.architecture.id, snapshot.version.id, frameworks))
      if (kind === 'azure') setAzurePreflight(await architectureApi.runAzurePreflight(snapshot.architecture.id, snapshot.version.id))
      if (kind === 'conformance' && azureSnapshotId) {
        const result = await architectureApi.runConformance(snapshot.architecture.id, snapshot.version.id, azureSnapshotId)
        setConformance(result)
        setConformanceHistory(await architectureApi.listConformance(snapshot.architecture.id, snapshot.version.id))
      }
      setAnalysisTab(kind)
    } catch (caught) {
      handleError(caught)
    } finally {
      setAnalysisLoading(false)
    }
  }

  async function compareConformance(fromId: string, toId: string) {
    if (!snapshot) return
    setAnalysisLoading(true)
    try {
      setDriftComparison(await architectureApi.compareConformance(snapshot.architecture.id, snapshot.version.id, fromId, toId))
    } catch (caught) {
      handleError(caught)
    } finally {
      setAnalysisLoading(false)
    }
  }

  async function runComparison() {
    if (!architectureId || !compareFrom || !compareTo) return
    setAnalysisLoading(true)
    try {
      setComparison(await architectureApi.compareVersions(architectureId, compareFrom, compareTo))
    } catch (caught) {
      handleError(caught)
    } finally {
      setAnalysisLoading(false)
    }
  }

  async function assertLatestDraft(currentArchitectureId: string, currentVersion: ArchitectureVersion) {
    const freshVersions = await architectureApi.listVersions(currentArchitectureId)
    const freshCurrent = freshVersions.find((item) => item.id === currentVersion.id)
    const latestSequence = Math.max(...freshVersions.map((item) => item.version_sequence ?? 0), 0)
    if (!freshCurrent || freshCurrent.status.toUpperCase() !== 'DRAFT' || (freshCurrent.version_sequence ?? 0) < latestSequence) {
      throw new ApiError(409, { code: 'VERSION_CONFLICT', message: 'This draft is no longer the latest architecture version. Local edits were preserved.' })
    }
  }

  async function reloadLatestVersion() {
    if (!architectureId) return
    const freshVersions = await architectureApi.listVersions(architectureId)
    setVersions(freshVersions)
    setVersionId(freshVersions.at(-1)?.id ?? '')
    setConflict(false)
  }

  const handleHistoryState = useCallback((undo: boolean, redo: boolean) => {
    setCanUndo(undo)
    setCanRedo(redo)
  }, [])

  const selected = snapshot?.resources.find((item) => item.id === selectedId) ?? null
  const relatedCount = snapshot ? snapshot.relationships.filter((item) => item.source_resource_id === selectedId || item.target_resource_id === selectedId).length : 0
  const affectedChildren = snapshot && deleteTarget ? snapshot.resources.filter((item) => item.parent_resource_id === deleteTarget.id) : []
  const rootContainer = Object.values(catalogDetails).find((item) => item.valid_parent_types.length === 0 && item.valid_child_types.length > 0) ?? null

  if (loading && !snapshot) return <div className="app-loading"><span className="brand-mark">AA</span><p>Loading architecture designer...</p></div>

  return <div className="app-shell">
    <ArchitectureHeader architectures={architectures} versions={versions} architectureId={architectureId} versionId={versionId} saveState={saveState} onArchitectureChange={setArchitectureId} onVersionChange={setVersionId} onCreateVersion={() => setShowNewVersion(true)} onCompare={() => setShowCompare(true)} onUndo={() => canvasRef.current?.undo()} onRedo={() => canvasRef.current?.redo()} canUndo={canUndo} canRedo={canRedo} />
    {error && <div className={`global-alert${conflict ? ' global-alert--conflict' : ''}`} role="alert"><span>{error}</span>{conflict && <><button onClick={() => void reloadLatestVersion()}>Reload latest</button><button onClick={() => setShowCompare(true)}>Compare</button></>}<button aria-label="Dismiss error" onClick={() => setError(null)}>×</button></div>}
    <div className="designer-grid">
      <ResourceCatalog resources={catalog} loading={loading} disabled={!snapshot || snapshot.version.status.toUpperCase() !== 'DRAFT'} />
      {snapshot ? <ArchitectureCanvas ref={canvasRef} snapshot={snapshot} catalog={catalogDetails} onSelect={setSelectedId} onDropResource={dropResource} onConnect={requestRelationship} onSaveState={setSaveState} onHistoryState={handleHistoryState} rootContainer={rootContainer} onBrowseCatalog={() => document.querySelector<HTMLInputElement>('.search-field input')?.focus()} /> : <main className="canvas-shell"><div className="canvas-empty"><strong>Select an architecture version</strong></div></main>}
      <PropertiesPanel resource={selected} catalog={selected ? catalogDetails[selected.resource_type] ?? null : null} readOnly={!snapshot || snapshot.version.status.toUpperCase() !== 'DRAFT'} relationshipCount={relatedCount} onSave={saveResource} onDelete={() => selected && setDeleteTarget(selected)} onClose={() => setSelectedId(null)} />
    </div>
    <section className="analysis-dock">
      <nav aria-label="Architecture analysis"><button className={analysisTab === 'validation' ? 'active' : ''} onClick={() => setAnalysisTab('validation')}><Activity size={16} />Validation</button><button className={analysisTab === 'compliance' ? 'active' : ''} onClick={() => setAnalysisTab('compliance')}><ShieldCheck size={16} />Compliance</button><button className={analysisTab === 'dependencies' ? 'active' : ''} onClick={() => setAnalysisTab('dependencies')}><GitBranch size={16} />Dependencies</button><button className={analysisTab === 'azure' ? 'active' : ''} onClick={() => setAnalysisTab('azure')}><CloudCog size={16} />Azure</button><button className={analysisTab === 'conformance' ? 'active' : ''} onClick={() => setAnalysisTab('conformance')}><ScanSearch size={16} />Drift</button></nav>
      {analysisTab === 'validation' && <ValidationPanel result={validation} loading={analysisLoading} onRun={() => void runAnalysis('validation')} />}
      {analysisTab === 'compliance' && <CompliancePanel result={compliance} loading={analysisLoading} onRun={(items) => void runAnalysis('compliance', items)} />}
      {analysisTab === 'dependencies' && <DependencyPanel result={dependencies} loading={analysisLoading} onRun={() => void runAnalysis('dependencies')} />}
      {analysisTab === 'azure' && <AzurePreflightPanel connection={azureStatus} result={azurePreflight} loading={analysisLoading} onRun={() => void runAnalysis('azure')} />}
      {analysisTab === 'conformance' && <ConformancePanel snapshots={azureSnapshots} snapshotId={azureSnapshotId} history={conformanceHistory} selected={conformance} comparison={driftComparison} loading={analysisLoading} onSnapshotChange={setAzureSnapshotId} onRun={() => void runAnalysis('conformance')} onSelect={setConformance} onCompare={(fromId, toId) => void compareConformance(fromId, toId)} />}
    </section>
    {showCompare && <VersionComparison versions={versions} fromId={compareFrom} toId={compareTo} result={comparison} loading={analysisLoading} onFromChange={setCompareFrom} onToChange={setCompareTo} onCompare={() => void runComparison()} onClose={() => setShowCompare(false)} />}
    {showNewVersion && <TextEntryDialog title="Create new version" label="Change description" placeholder="Describe the intended architecture change" submitLabel="Create draft" onCancel={() => setShowNewVersion(false)} onSubmit={(value) => void submitNewVersion(value)} />}
    {pendingConnection && <TextEntryDialog title="Create relationship" label="Relationship type" placeholder="Enter the backend relationship type" submitLabel="Create relationship" onCancel={() => setPendingConnection(null)} onSubmit={(value) => void submitRelationship(value)} />}
    {deleteTarget && <DeleteConfirmation resource={deleteTarget} affected={affectedChildren} onCancel={() => setDeleteTarget(null)} onConfirm={() => void confirmDelete()} />}
  </div>
}
