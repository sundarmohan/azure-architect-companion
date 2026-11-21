import { AlertTriangle, CheckCircle2, CloudOff, Info } from 'lucide-react'
import type { AzureConnectionStatus, AzurePreflightResult } from '../../models/analysis'

interface AzurePreflightPanelProps {
  connection: AzureConnectionStatus | null
  result: AzurePreflightResult | null
  loading: boolean
  onRun: () => void
}

export function AzurePreflightPanel({ connection, result, loading, onRun }: AzurePreflightPanelProps) {
  const connected = connection?.status === 'CONNECTED'
  return <section className="analysis-panel" aria-label="Azure preflight findings">
    <div className="analysis-panel__header"><div><strong>Azure preflight</strong><small>{connection?.message ?? 'Azure connection status unavailable'}</small></div><button className="secondary-button" onClick={onRun} disabled={loading || !connected}>{loading ? 'Checking...' : 'Run preflight'}</button></div>
    {!connected && <p className="panel-message"><CloudOff size={16} /> {connection?.status ?? 'UNAVAILABLE'}</p>}
    {connected && !result && <p className="panel-message">Check this version against the latest explicit Azure intelligence snapshot.</p>}
    {result && <div className="findings">{result.findings.map((finding, index) => { const Icon = finding.severity === 'INFO' ? Info : AlertTriangle; return <article className={`finding finding--${finding.severity.toLowerCase()}`} key={`${finding.code}-${index}`}><Icon size={17} /><div><strong>{finding.severity} · AZURE</strong><p>{finding.message}</p><small>{finding.code}</small></div></article> })}{result.findings.length === 0 && <p className="empty-success"><CheckCircle2 size={18} />Azure preflight passed.</p>}</div>}
  </section>
}