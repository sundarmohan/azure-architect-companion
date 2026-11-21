import { AlertTriangle, CheckCircle2, GitCompareArrows, History } from 'lucide-react'
import type { AzureSnapshotSummary, ConformanceAssessment, DriftHistoryComparison } from '../../models/analysis'

interface ConformancePanelProps {
  snapshots: AzureSnapshotSummary[]
  snapshotId: string
  history: ConformanceAssessment[]
  selected: ConformanceAssessment | null
  comparison: DriftHistoryComparison | null
  loading: boolean
  onSnapshotChange: (id: string) => void
  onRun: () => void
  onSelect: (assessment: ConformanceAssessment) => void
  onCompare: (fromId: string, toId: string) => void
}

export function ConformancePanel({ snapshots, snapshotId, history, selected, comparison, loading, onSnapshotChange, onRun, onSelect, onCompare }: ConformancePanelProps) {
  const compareFrom = history[1]?.id
  const compareTo = history[0]?.id
  return <section className="analysis-panel" aria-label="Conformance and drift">
    <div className="analysis-panel__header"><div><strong>Conformance and drift</strong><small>Canonical architecture compared with normalized M10 evidence</small></div><div className="inline-actions"><select aria-label="Azure snapshot" value={snapshotId} onChange={(event) => onSnapshotChange(event.target.value)}><option value="">Select Azure snapshot</option>{snapshots.map((item) => <option key={item.id} value={item.id}>S{item.snapshot_sequence} · {item.freshness}</option>)}</select><button className="secondary-button" onClick={onRun} disabled={loading || !snapshotId}>{loading ? 'Checking...' : 'Run check'}</button></div></div>
    {selected ? <><div className="conformance-summary"><strong>CONFORMANCE: {selected.overall_status}</strong><span>Snapshot {selected.azure_snapshot_id}</span>{(['conformant', 'modified', 'missing', 'unexpected', 'unknown'] as const).map((key) => <span key={key}>{key}: {selected.summary[key]}</span>)}</div><div className="findings">{selected.findings.map((finding) => { const Icon = finding.status === 'CONFORMANT' ? CheckCircle2 : AlertTriangle; return <article className={`finding finding--${finding.severity.toLowerCase()}`} key={finding.id}><Icon size={17} /><div><strong>{finding.status} · {finding.category}</strong><p>{finding.resource_key ?? finding.resource_type ?? 'Azure resource'}: {finding.explanation}</p>{finding.property_path && <small>{finding.property_path}</small>}<Value label="Desired" value={finding.desired_value_safe} /><Value label="Actual" value={finding.actual_value_safe} /></div></article> })}</div></> : <p className="panel-message">Run a check or select a historical assessment.</p>}
    {history.length > 0 && <div className="conformance-history"><strong><History size={15} /> History</strong>{history.map((item) => <button className="secondary-button" key={item.id} onClick={() => onSelect(item)}>{new Date(item.created_at).toLocaleString()} · {item.overall_status}</button>)}{compareFrom && compareTo && <button className="secondary-button" onClick={() => onCompare(compareFrom, compareTo)}><GitCompareArrows size={15} />Compare latest</button>}</div>}
    {comparison && <div className="comparison-counts"><span>New drift: {comparison.new_drift.length}</span><span>Resolved: {comparison.resolved_drift.length}</span><span>Persistent: {comparison.persistent_drift.length}</span></div>}
  </section>
}

function Value({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined) return null
  return <small>{label}: {typeof value === 'string' ? value : JSON.stringify(value)}</small>
}