import { AlertTriangle, CheckCircle2, Info } from 'lucide-react'
import type { ValidationResult } from '../../models/analysis'

export function ValidationPanel({ result, loading, onRun }: { result: ValidationResult | null; loading: boolean; onRun: () => void }) {
  return <section className="analysis-panel" aria-label="Validation findings"><div className="analysis-panel__header"><div><strong>Architecture validation</strong><small>Structural and technical checks</small></div><button className="secondary-button" onClick={onRun} disabled={loading}>{loading ? 'Running...' : 'Validate'}</button></div>
    {!result && <p className="panel-message">Run backend validation for this version.</p>}
    {result && <div className="findings">{result.findings.map((finding, index) => { const Icon = finding.severity === 'ERROR' ? AlertTriangle : finding.severity === 'WARNING' ? AlertTriangle : Info; return <article className={`finding finding--${finding.severity.toLowerCase()}`} key={`${finding.code}-${index}`}><Icon size={17} /><div><strong>{finding.severity} · {finding.category}</strong><p>{finding.message}</p><small>{finding.code}</small></div></article> })}{result.findings.length === 0 && <p className="empty-success"><CheckCircle2 size={18} />No validation findings.</p>}</div>}
  </section>
}
