import type { DependencyAnalysis } from '../../models/analysis'

export function DependencyPanel({ result, loading, onRun }: { result: DependencyAnalysis | null; loading: boolean; onRun: () => void }) {
  const groups = ['REQUIRED', 'RECOMMENDED', 'OPTIONAL'] as const
  return <section className="analysis-panel" aria-label="Dependency findings"><div className="analysis-panel__header"><div><strong>Dependency findings</strong><small>Backend catalog analysis</small></div><button className="secondary-button" onClick={onRun} disabled={loading}>{loading ? 'Analyzing...' : 'Analyze'}</button></div>
    {!result && <p className="panel-message">Analyze required, recommended, and optional dependencies.</p>}
    {result && groups.map((group) => { const findings = result.findings.filter((item) => item.classification === group && item.status !== 'SATISFIED'); return <div className="dependency-group" key={group}><h3>{group} <span>{findings.length}</span></h3>{findings.map((finding, index) => <article key={`${finding.source_resource_key}-${index}`}><strong>{finding.source_resource_key}</strong><p>{finding.dependency_resource_type ?? 'Unknown catalog resource'}</p><small>{finding.reason}</small></article>)}{findings.length === 0 && <p className="field-note">No missing {group.toLowerCase()} dependencies.</p>}</div> })}
  </section>
}
