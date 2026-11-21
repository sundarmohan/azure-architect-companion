import { useState } from 'react'
import type { ComplianceResult } from '../../models/analysis'

const frameworks = ['HIPAA', 'GDPR', 'SOC2', 'ISO27001', 'NIST', 'HITRUST']

export function CompliancePanel({ result, loading, onRun }: { result: ComplianceResult | null; loading: boolean; onRun: (frameworks: string[]) => void }) {
  const [selected, setSelected] = useState<string[]>(['SOC2'])
  return <section className="analysis-panel" aria-label="Technical compliance evaluation"><div className="analysis-panel__header"><div><strong>Technical control evaluation</strong><small>Not legal certification</small></div><button className="secondary-button" disabled={loading || selected.length === 0} onClick={() => onRun(selected)}>{loading ? 'Evaluating...' : 'Evaluate'}</button></div>
    <div className="framework-options">{frameworks.map((item) => <label key={item}><input type="checkbox" checked={selected.includes(item)} onChange={() => setSelected((current) => current.includes(item) ? current.filter((value) => value !== item) : [...current, item])} />{item}</label>)}</div>
    {result?.evaluations.map((evaluation) => <div className="evaluation" key={evaluation.framework_name}><h3>{evaluation.framework_name} <span>{evaluation.overall_status}</span></h3>{evaluation.findings.map((finding) => <article className={`finding finding--${finding.outcome.toLowerCase()}`} key={finding.control_code}><div><strong>{finding.outcome} · {finding.control_code}</strong><p>{finding.message}</p></div></article>)}</div>)}
  </section>
}
