import { useEffect, useMemo, useState } from "react";
import { connectMonitoringSubscription, discoverMonitoringSubscriptions, getMonitoringMetrics, getSettingsOverview, listMonitoringSubscriptions, refreshMonitoringSubscription, updateMonitoringSubscriptionIncidentStatus } from "../services/api";

const TABS = [["resources", "Resources"], ["metrics", "Metrics"], ["alerts", "Alerts"], ["incidents", "Incidents"], ["unused", "Unused Resources"]];

function statusLabel(value) { return String(value || "unknown").replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function StatusBadge({ value }) {
  const state = String(value || "unknown").toLowerCase();
  const tone = state === "healthy" || state === "connected" || state === "available" || state === "evaluated" || state === "resolved" ? "good" : ["unknown", "not_checked", "no_data", "unsupported"].includes(state) ? "muted" : ["warning", "degraded", "acknowledged", "medium"].includes(state) ? "warn" : "bad";
  return <span className={`monitor-badge ${tone}`}>{statusLabel(value)}</span>;
}
function formatDate(value) {
  if (!value) return "Not checked yet";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not available" : date.toLocaleString();
}

function readableMetricName(value) {
  return String(value || "Metric").replaceAll("_", " ").replace(/([a-z])([A-Z])/g, "$1 $2").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatMetricValue(value, unit) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "No data";
  const number = Number(value); const normalized = String(unit || "").toLowerCase();
  if (normalized.includes("byte") && Math.abs(number) >= 1024) {
    const units = ["B", "KB", "MB", "GB", "TB"]; let scaled = Math.abs(number); let index = 0;
    while (scaled >= 1024 && index < units.length - 1) { scaled /= 1024; index += 1; }
    return `${number < 0 ? "-" : ""}${scaled.toFixed(scaled >= 100 ? 0 : scaled >= 10 ? 1 : 2)} ${units[index]}`;
  }
  if (normalized.includes("percent")) return `${number.toFixed(2)}%`;
  if (normalized.includes("millisecond")) return `${number.toLocaleString(undefined, { maximumFractionDigits: 2 })} ms`;
  if (normalized.includes("count") || normalized === "count") return number.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return number.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function metricTrend(points) {
  if (!points || points.length < 2) return "Stable";
  const first = Number(points[0].value); const last = Number(points[points.length - 1].value);
  if (!Number.isFinite(first) || !Number.isFinite(last)) return "Stable";
  const baseline = Math.max(Math.abs(first), Math.abs(last), 1); const delta = (last - first) / baseline;
  return delta > 0.05 ? "Increasing" : delta < -0.05 ? "Decreasing" : "Stable";
}

function metricRisk(resource, metric) {
  if (!metric?.points?.length) return "no_data";
  const status = String(resource.status || "unknown").toLowerCase();
  if (["unavailable", "critical", "down"].includes(status)) return "critical";
  if (["degraded", "warning"].includes(status)) return "warning";
  return "healthy";
}

const RISK_ORDER = { critical: 0, warning: 1, healthy: 2, no_data: 3 };

function MetricChart({ points }) {
  if (!points?.length) return <div className="metric-chart-empty">No historical data</div>;
  const values = points.map((point) => Number(point.value)).filter(Number.isFinite); const min = Math.min(...values); const max = Math.max(...values); const span = max - min || 1;
  const coordinates = points.map((point, index) => `${(index / Math.max(points.length - 1, 1)) * 100},${96 - ((Number(point.value) - min) / span) * 82}`).join(" ");
  return <div className="metric-chart" aria-label="Metric time series chart"><svg viewBox="0 0 100 100" role="img" preserveAspectRatio="none"><polyline className="monitor-chart-line" points={coordinates} /></svg><div className="monitor-chart-scale"><span>{formatDate(points[0].timestamp)}</span><span>{formatDate(points[points.length - 1].timestamp)}</span></div></div>;
}

export default function MonitoringWorkspace() {
  const [saved, setSaved] = useState([]); const [selectedId, setSelectedId] = useState(""); const [settings, setSettings] = useState(null);
  const [available, setAvailable] = useState([]); const [principal, setPrincipal] = useState(""); const [toConnect, setToConnect] = useState("");
  const [tab, setTab] = useState("resources"); const [range, setRange] = useState("24"); const [metricSort, setMetricSort] = useState("risk"); const [metricDescending, setMetricDescending] = useState(false); const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(""); const [error, setError] = useState("");
  const selected = useMemo(() => saved.find((item) => item.id === selectedId) || saved[0] || null, [saved, selectedId]);
  const azureConfigured = settings?.azure_integration?.configuration_state === "configured";

  async function load() {
    setLoading(true); setError("");
    try { const [subscriptions, overview] = await Promise.all([listMonitoringSubscriptions(), getSettingsOverview()]); setSaved(subscriptions); setSettings(overview); setSelectedId((current) => current || subscriptions[0]?.id || ""); }
    catch (err) { setError(err.message || "Unable to load Monitoring."); } finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);
  async function findSubscriptions() { setBusy("discover"); setError(""); try { setAvailable(await discoverMonitoringSubscriptions()); } catch (err) { setError(err.message || "Azure subscription discovery failed."); } finally { setBusy(""); } }
  async function connect() {
    const candidate = available.find((item) => item.subscription_id === toConnect); if (!candidate) return;
    setBusy("connect"); setError("");
    try { const connected = await connectMonitoringSubscription({ subscription_id: candidate.subscription_id, name: candidate.name, tenant_id: candidate.tenant_id }); setSaved((current) => [connected, ...current.filter((item) => item.id !== connected.id)]); setSelectedId(connected.id); setToConnect(""); setAvailable([]); }
    catch (err) { setError(err.message || "Subscription connection failed."); } finally { setBusy(""); }
  }
  async function refresh() {
    if (!selected) return; setBusy("refresh"); setError("");
    try { const next = await refreshMonitoringSubscription(selected.id); setSaved((current) => current.map((item) => item.id === next.id ? next : item)); }
    catch (err) { setError(err.message || "Monitoring refresh failed."); } finally { setBusy(""); }
  }
  async function loadMetrics() {
    if (!selected) return; setBusy("metrics"); setError("");
    try { const next = await getMonitoringMetrics(selected.id, Number(range), range === "1" ? "PT5M" : range === "6" ? "PT15M" : range === "24" ? "PT1H" : range === "168" ? "PT6H" : range === "336" ? "PT12H" : "P1D"); setSaved((current) => current.map((item) => item.id === next.id ? next : item)); }
    catch (err) { setError(err.message || "Metric retrieval failed."); } finally { setBusy(""); }
  }
  useEffect(() => {
    if (tab === "metrics" && selected) loadMetrics();
  }, [tab, range, selected?.id]);
  async function updateIncident(incident, status) {
    if (!selected) return; setBusy(`incident-${incident.id}`); setError("");
    try { const next = await updateMonitoringSubscriptionIncidentStatus(selected.id, incident.id, { status }); setSaved((current) => current.map((item) => item.id === next.id ? next : item)); }
    catch (err) { setError(err.message || "Incident update failed."); } finally { setBusy(""); }
  }
  function renderTab() {
    if (tab === "resources") return <section className="card monitor-card-compact"><div className="card-title"><h2>Resources</h2><span>{selected.total_resources} discovered</span></div>{!selected.resources.length ? <div className="empty">Azure returned no resources for this subscription, or the latest refresh could not retrieve them.</div> : <div className="monitor-table-shell"><table className="table monitor-resource-table"><thead><tr><th>Name</th><th>Type</th><th>Resource group</th><th>Region</th><th>Status</th><th>Last checked</th></tr></thead><tbody>{selected.resources.map((resource) => <tr key={resource.id}><td>{resource.name}</td><td>{resource.resource_type}</td><td>{resource.resource_group || "Not reported"}</td><td>{resource.region || "Not reported"}</td><td><StatusBadge value={resource.status} />{resource.status_source && <div className="monitor-inline-help">{resource.status_source}</div>}</td><td>{formatDate(resource.last_checked)}</td></tr>)}</tbody></table></div>}</section>;
    if (tab === "metrics") {
      const metricRows = selected.resources.flatMap((resource) => (resource.metrics?.length ? resource.metrics : [{ name: "No applicable metric data", unit: null, points: [] }]).map((metric) => ({ resource, metric, risk: metricRisk(resource, metric), trend: metricTrend(metric.points) })));
      const resourceRisk = selected.resources.reduce((result, resource) => { const risks = metricRows.filter((row) => row.resource.id === resource.id).map((row) => row.risk); result[resource.id] = risks.sort((a, b) => RISK_ORDER[a] - RISK_ORDER[b])[0] || "no_data"; return result; }, {});
      const riskCounts = Object.values(resourceRisk).reduce((result, risk) => ({ ...result, [risk]: (result[risk] || 0) + 1 }), { critical: 0, warning: 0, healthy: 0, no_data: 0 });
      const sortedRows = [...metricRows].sort((a, b) => {
        if (metricSort === "risk") return RISK_ORDER[a.risk] - RISK_ORDER[b.risk] || a.resource.name.localeCompare(b.resource.name);
        const left = metricSort === "latest" ? Number(a.metric.points?.at(-1)?.value ?? -Infinity) : String(metricSort === "resource" ? a.resource.name : metricSort === "metric" ? a.metric.name : a.metric.unit || "");
        const right = metricSort === "latest" ? Number(b.metric.points?.at(-1)?.value ?? -Infinity) : String(metricSort === "resource" ? b.resource.name : metricSort === "metric" ? b.metric.name : b.metric.unit || "");
        const comparison = typeof left === "number" ? left - right : left.localeCompare(right); return metricDescending ? -comparison : comparison;
      });
      const sortBy = (key) => { if (key === "risk") { setMetricSort("risk"); setMetricDescending(false); return; } setMetricDescending((current) => metricSort === key ? !current : false); setMetricSort(key); };
      const sortableHeader = (label, key) => <button className="monitor-sort" onClick={() => sortBy(key)}>{label}{metricSort === key ? (metricDescending ? " ↓" : " ↑") : ""}</button>;
      return <section className="card monitor-card-compact metrics-panel"><div className="card-title"><div><h2>Metrics</h2><p className="monitor-subtitle">Risk is based on Azure Resource Health; metric magnitude alone is never treated as a failure.</p></div><div className="toolbar-row"><select aria-label="Metric time range" value={range} onChange={(event) => setRange(event.target.value)}><option value="1">1h</option><option value="6">6h</option><option value="24">24h</option><option value="168">7d</option><option value="336">14d</option><option value="720">30d</option></select><button onClick={loadMetrics} disabled={!selected || busy}>{busy === "metrics" ? "Loading..." : "Refresh metrics"}</button></div></div><div className="metrics-risk-summary"><div className="metrics-risk-card critical"><span>Critical</span><strong>{riskCounts.critical}</strong></div><div className="metrics-risk-card warning"><span>Warning</span><strong>{riskCounts.warning}</strong></div><div className="metrics-risk-card healthy"><span>Healthy</span><strong>{riskCounts.healthy}</strong></div><div className="metrics-risk-card no-data"><span>No Data</span><strong>{riskCounts.no_data}</strong></div></div><div className="metrics-state-line"><StatusBadge value={selected.metrics_state} />{selected.metrics_state === "unsupported" ? <span>Some selected resource types do not expose Azure Monitor metrics.</span> : selected.metrics_state === "permission_failure" ? <span>Permission error: Azure Monitor access was denied.</span> : selected.metrics_state === "authentication_failure" ? <span>Authentication error while reading Azure Monitor.</span> : selected.metrics_state !== "available" ? <span>No Azure metric data is available for this time range.</span> : <span>{metricRows.filter((row) => row.metric.points?.length).length} metric series with historical points.</span>}</div>{selected.metrics_state === "available" || metricRows.length ? <div className="monitor-table-shell"><table className="table monitor-metric-table metrics-risk-table"><thead><tr><th>{sortableHeader("Risk", "risk")}</th><th>{sortableHeader("Resource", "resource")}</th><th>Resource Type</th><th>{sortableHeader("Metric", "metric")}</th><th>{sortableHeader("Latest Value", "latest")}</th><th>{sortableHeader("Unit", "unit")}</th><th>Trend</th><th>Last Updated</th></tr></thead><tbody>{sortedRows.map(({ resource, metric, risk, trend }) => { const point = metric.points?.at(-1); return <tr key={`${resource.id}-${metric.name}`}><td><StatusBadge value={risk} /></td><td title={resource.name}>{resource.name}</td><td title={resource.resource_type}>{readableMetricName(resource.resource_type)}</td><td title={metric.name}>{readableMetricName(metric.name)}</td><td className="metric-latest" title={point ? `Raw Azure value: ${point.value}` : undefined}>{formatMetricValue(point?.value, metric.unit)}</td><td>{metric.unit || "Not reported"}</td><td><span className={`metric-trend ${trend.toLowerCase()}`}>{trend}</span></td><td className="metric-detail-cell"><span>{point ? formatDate(point.timestamp) : "No data"}</span><details><summary>View history</summary><div className="metric-detail"><div className="metric-detail-summary"><strong>Current: {formatMetricValue(point?.value, metric.unit)}</strong><span>Trend: {trend}</span><span>Threshold: {metric.threshold ?? "Not provided by Azure"}</span></div><MetricChart points={metric.points} /><div className="metric-history">{(metric.points || []).map((seriesPoint) => <div key={`${seriesPoint.timestamp}-${seriesPoint.value}`}><time>{formatDate(seriesPoint.timestamp)}</time><strong title={`Raw Azure value: ${seriesPoint.value}`}>{formatMetricValue(seriesPoint.value, metric.unit)}</strong><span>{seriesPoint.value}</span></div>)}</div></div></details></td></tr>; })}</tbody></table></div> : null}</section>;
    }
    if (tab === "alerts") return <section className="card monitor-card-compact"><div className="card-title"><h2>Alerts</h2><StatusBadge value={selected.alerts_state} /></div>{selected.alerts_state === "permission_failure" ? <div className="empty">Permission error: Azure Monitor Alerts access was denied.</div> : selected.alerts_state !== "available" && selected.alerts_state !== "provider_error" ? <div className="empty">No active alerts</div> : selected.alerts_state === "provider_error" ? <div className="empty">Azure API error while retrieving alerts.</div> : !selected.alerts.length ? <div className="empty">No active alerts</div> : <div className="monitor-table-shell"><table className="table monitor-alert-table"><thead><tr><th>Alert name</th><th>Severity</th><th>Status</th><th>Resource</th><th>Condition / rule</th><th>Fired time</th><th>Last updated</th></tr></thead><tbody>{selected.alerts.map((alert) => <tr key={alert.id}><td>{alert.name}</td><td><StatusBadge value={alert.severity} /></td><td><StatusBadge value={alert.status} /></td><td>{alert.resource_name || alert.resource_id || "Not reported"}</td><td>{alert.condition || alert.description || "Not reported"}</td><td>{formatDate(alert.fired_time || alert.timestamp)}</td><td>{formatDate(alert.last_updated)}</td></tr>)}</tbody></table></div>}</section>;
    if (tab === "incidents") return <section className="card monitor-card-compact"><div className="card-title"><h2>Incidents</h2><StatusBadge value={selected.incidents_state} /></div>{selected.incidents_state !== "available" ? <div className="empty">No incidents</div> : !selected.incidents.length ? <div className="empty">No incidents</div> : <div className="monitor-table-shell"><table className="table monitor-incident-table"><thead><tr><th>Incident</th><th>Resource</th><th>Severity</th><th>Status</th><th>Created</th><th>Updated</th><th>Details / timeline</th><th>Lifecycle</th></tr></thead><tbody>{selected.incidents.map((incident) => <tr key={incident.id}><td><strong>{incident.title}</strong></td><td>{incident.resource_ids?.join(", ") || "Not reported"}</td><td><StatusBadge value={incident.severity} /></td><td><StatusBadge value={incident.status} /></td><td>{formatDate(incident.created_at)}</td><td>{formatDate(incident.updated_at)}</td><td><details><summary>View details ({incident.timeline?.length || 0} events)</summary><div>{incident.description}</div>{(incident.timeline || []).map((event) => <div key={`${event.timestamp}-${event.event_type}`}>{formatDate(event.timestamp)}: {event.details}</div>)}</details></td><td><div className="toolbar-row"><button onClick={() => updateIncident(incident, "open")} disabled={busy}>Open</button><button onClick={() => updateIncident(incident, "acknowledged")} disabled={busy}>Acknowledge</button><button onClick={() => updateIncident(incident, "resolved")} disabled={busy}>Resolve</button></div></td></tr>)}</tbody></table></div>}</section>;
    const analysis = selected.unused_analysis || {};
    return <section className="card"><div className="card-title"><h2>Unused Resources</h2><StatusBadge value={analysis.state} /></div>{analysis.state === "no_data" ? <div className="empty">Insufficient data: no real Azure resources were available for analysis.</div> : !analysis.findings?.length ? <div className="empty">No unused resources found in the available Azure utilization/configuration data.</div> : <div className="monitor-table-shell"><table className="table"><thead><tr><th>Resource</th><th>Reason</th><th>Confidence</th><th>Signals</th><th>Estimated waste</th></tr></thead><tbody>{analysis.findings.map((finding) => <tr key={finding.azure_resource_id}><td>{finding.resource_name}</td><td>{finding.idle_reason}</td><td><StatusBadge value={finding.confidence} /></td><td>{finding.idle_signals?.join(", ") || "Not available"}</td><td>{finding.monthly_cost_estimate ? `$${Number(finding.monthly_cost_estimate).toFixed(2)}` : "Not available"}</td></tr>)}</tbody></table></div>}</section>;
  }
  if (loading && saved.length === 0) return <section className="workspace-panel"><div className="card">Loading saved Azure monitoring connections...</div></section>;

  return <section className="workspace-panel">
    <header className="workspace-header"><div><div className="workspace-eyebrow">Azure Monitoring</div><h1>Resource health</h1><p>Saved subscriptions are monitored by the backend. This page reads the latest persisted Azure results.</p></div><div className="toolbar-row"><button className="primary" onClick={refresh} disabled={!selected || busy}>{busy === "refresh" ? "Refreshing..." : "Refresh now"}</button></div></header>
    {error && <div className="notice error">{error}</div>}
    {!azureConfigured && <div className="card"><h2>Connect Azure Subscription</h2><p>Configure an Azure service principal in Settings first. Monitoring never asks for or exposes its secret.</p></div>}
    {azureConfigured && <section className="card"><div className="card-title"><h2>Connect Azure Subscription</h2><StatusBadge value="configured" /></div><div className="toolbar-row"><select aria-label="Service principal" value={principal} onChange={(event) => setPrincipal(event.target.value)}><option value="">Select Service Principal from Settings</option><option value="azure_credentials">Azure Service Principal ({settings.azure_integration.configured_client_id_hint || "configured"})</option></select><button onClick={findSubscriptions} disabled={!principal || busy}>{busy === "discover" ? "Authenticating..." : "Retrieve subscriptions"}</button><select aria-label="Available Azure subscription" value={toConnect} onChange={(event) => setToConnect(event.target.value)} disabled={!available.length}><option value="">Select accessible subscription</option>{available.map((item) => <option key={item.subscription_id} value={item.subscription_id}>{item.name} ({item.subscription_id})</option>)}</select><button className="primary" onClick={connect} disabled={!toConnect || busy}>{busy === "connect" ? "Saving..." : "Save subscription"}</button></div></section>}
    {!saved.length ? <div className="card empty">No Azure subscriptions are connected. Use the connection flow above to select an accessible subscription.</div> : <>
      <section className="card"><div className="card-title"><h2>Azure Account</h2><StatusBadge value={selected?.connection_status} /></div><div className="toolbar-row"><label htmlFor="monitor-subscription">Subscription</label><select id="monitor-subscription" value={selected?.id || ""} onChange={(event) => setSelectedId(event.target.value)}>{saved.map((item) => <option key={item.id} value={item.id}>{item.name} ({item.subscription_id})</option>)}</select></div>{selected?.connection_message && <p className="notice error">{selected.connection_message}</p>}{selected?.refresh_error && selected?.last_successful_at && <p className="notice warning">Showing stale data from the last successful refresh on {formatDate(selected.last_successful_at)}.</p>}</section>
      <div className="platform-grid"><article className="platform-card"><h3>Subscription</h3><div className="platform-value">{selected.name}</div><p>{selected.subscription_id}</p></article><article className="platform-card"><h3>Total resources</h3><div className="platform-value">{selected.total_resources}</div><p>Latest persisted inventory</p></article><article className="platform-card"><h3>Healthy / Warning / Critical / Unknown</h3><div className="platform-value">{selected.healthy_count} / {selected.warning_count} / {selected.critical_count} / {selected.unknown_count}</div><p>Azure Resource Health where reported</p></article><article className="platform-card"><h3>Last checked</h3><div className="platform-value">{formatDate(selected.last_checked_at)}</div><p>Backend refresh timestamp</p></article></div>
      <div className="monitor-tabs">{TABS.map(([id, label]) => <button key={id} className={`monitor-tab ${tab === id ? "active" : ""}`} onClick={() => setTab(id)}>{label}</button>)}</div>
      {renderTab()}
    </>}
  </section>;
}
