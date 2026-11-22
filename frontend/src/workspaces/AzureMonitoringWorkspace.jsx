import { useEffect, useMemo, useRef, useState } from "react";
import {
  getAzureMonitoring,
  getAzureMonitoringSchedule,
  refreshAzureMonitoring,
  updateAzureMonitoringSchedule,
} from "../services/api";
import AzureSnapshotWorkspace, { displayLabel, snapshotTime } from "./AzureSnapshotWorkspace";
import AzureDiagnostics from "./AzureDiagnostics";

const NUMBER_FORMAT = new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 });

function formatMetric(value, unit) {
  return [NUMBER_FORMAT.format(value), unit].filter(Boolean).join(" ");
}

function MetricSeries({ metric }) {
  const points = (metric.points || [])
    .filter((point) => Number.isFinite(point.value) && point.timestamp && Number.isFinite(Date.parse(point.timestamp)))
    .map((point) => ({ ...point, time: Date.parse(point.timestamp) }))
    .sort((left, right) => left.time - right.time);
  const first = points[0];
  const latest = points.at(-1);
  const values = points.map(({ value }) => value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const line = points.map(({ time, value }) => [
    2 + ((time - first.time) / (latest.time - first.time || 1)) * 96,
    max === min ? 25 : 47 - ((value - min) / (max - min)) * 44,
  ].join(",")).join(" ");

  return <details className="metric-series">
    <summary><strong>{metric.name}</strong><span>{latest ? formatMetric(latest.value, metric.unit) : "No data"}</span></summary>
    {metric.aggregation && <p>Aggregation {displayLabel(metric.aggregation)}</p>}
    {latest && <>
      <p>Latest sample {snapshotTime(latest.timestamp)}</p>
      {points.length > 1 && <svg className="monitoring-trend" viewBox="0 0 100 50" preserveAspectRatio="none" aria-hidden="true">
        <polyline points={line} />
      </svg>}
      <div className="design-table">
        <table className="table">
          <thead><tr><th scope="col">Sample time</th><th scope="col">Value</th></tr></thead>
          <tbody>{points.slice(-12).reverse().map((point, index) => <tr key={`${point.timestamp}-${index}`}>
            <td>{snapshotTime(point.timestamp)}</td>
            <td>{formatMetric(point.value, metric.unit)}</td>
          </tr>)}</tbody>
        </table>
      </div>
      {points.length > 12 && <p>Showing the 12 most recent samples in the table.</p>}
    </>}
  </details>;
}

function HealthTriage({ snapshot, resources, onSelect }) {
  const confirmed = resources.filter((resource) => resource.health_status === "synced" &&
    ["available", "degraded", "unavailable"].includes(resource.health));
  const findings = confirmed.filter((resource) => resource.health !== "available");
  const retained = snapshot.status !== "synced" && Boolean(snapshot.last_success_at);

  return <section className="card account-form">
    <h2>Resource health triage</h2>
    {retained
      ? <p>Retained evidence from {snapshotTime(snapshot.last_success_at)}. The latest collection did not complete.</p>
      : snapshot.status === "partial_failure"
        ? <p>Incomplete evidence from the collection attempted at {snapshotTime(snapshot.last_attempt_at)}.</p>
        : snapshot.status === "synced" && <p>Snapshot collected {snapshotTime(snapshot.last_success_at)}.</p>}
    {resources.length > 0 && <p>Azure Resource Health confirmed the state of {confirmed.length} of {resources.length} sampled resources.</p>}
    {findings.length > 0 ? <div className="design-table">
      <table className="table" aria-label="Confirmed Azure resource health issues">
        <thead><tr><th scope="col">Resource</th><th scope="col">Reported health</th><th scope="col">Location</th></tr></thead>
        <tbody>{findings.map((resource) => <tr key={resource.id}>
          <td><button type="button" className="dismiss" onClick={() => onSelect(resource.id)}>
            Review {resource.name || resource.id}
          </button></td>
          <td>{displayLabel(resource.health)}</td>
          <td>{resource.location || "Unknown"}</td>
        </tr>)}</tbody>
      </table>
    </div> : <p>{confirmed.length ? "No degraded or unavailable resources in the confirmed evidence."
      : "No confirmed resource health evidence is available."}</p>}
  </section>;
}

function MonitoringResources({ snapshot }) {
  const [filter, setFilter] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const detailsHeading = useRef(null);
  const resources = snapshot.resources || [];
  const query = filter.trim().toLowerCase();
  const matching = useMemo(() => resources.filter((resource) => !query ||
    [resource.name, resource.type, resource.location, resource.health].some((value) =>
      value?.toLowerCase().includes(query))), [query, resources]);
  const selected = matching.find(({ id }) => id === selectedId) || matching[0];

  return <>
    <HealthTriage snapshot={snapshot} resources={resources} onSelect={(id) => {
      setFilter("");
      setSelectedId(id);
      detailsHeading.current?.focus();
    }} />
    <section className="card account-form">
      <h2 ref={detailsHeading} tabIndex={-1}>Resource health and metrics ({resources.length})</h2>
      {snapshot.limitations?.length > 0 && <ul>{snapshot.limitations.map((item) => <li key={item}>{item}</li>)}</ul>}
      {resources.length > 0 && <label>Filter monitored resources<input value={filter}
        onChange={(event) => setFilter(event.target.value)} placeholder="Name, resource type, location, or health" /></label>}
      {matching.length > 0 && <label>Resource<select value={selected.id} onChange={(event) => setSelectedId(event.target.value)}>
        {matching.map((resource) => <option key={resource.id} value={resource.id}>{resource.name} · {displayLabel(resource.health)}</option>)}
      </select></label>}
      {selected ? <div className="account-form">
        <h3>{selected.name}</h3>
        <dl className="design-meta">
          <div><dt>Resource type</dt><dd>{selected.type || "Unknown"}</dd></div>
          <div><dt>Location</dt><dd>{selected.location || "Unknown"}</dd></div>
          <div><dt>Azure Resource Health</dt><dd>{displayLabel(selected.health)}</dd></div>
          {selected.health_status && <div><dt>Health collection</dt><dd>{displayLabel(selected.health_status)}</dd></div>}
          {selected.metrics_status && <div><dt>Metrics collection</dt><dd>{displayLabel(selected.metrics_status)}</dd></div>}
        </dl>
        {selected.metrics?.length ? <div className="account-form" key={selected.id}>{selected.metrics.map((metric) =>
          <MetricSeries key={`${metric.name}-${metric.aggregation || ""}`} metric={metric} />)}</div>
          : <p>No metrics were returned for this resource.</p>}
      </div> : <p>{resources.length ? "No resources match the filter." : "No monitoring data has been collected."}</p>}
    </section>
  </>;
}

function MonitoringSchedule({ subscription }) {
  const [schedule, setSchedule] = useState(null);
  const [enabled, setEnabled] = useState(false);
  const [includeSecurity, setIncludeSecurity] = useState(false);
  const [interval, setInterval] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");

  useEffect(() => {
    let active = true;
    getAzureMonitoringSchedule(subscription).then((data) => {
      if (!active) return;
      setSchedule(data);
      setEnabled(data.enabled);
      setIncludeSecurity(data.include_security ?? false);
      setInterval(String(data.interval_minutes));
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") setError(failure.message);
    });
    return () => { active = false; };
  }, [subscription]);

  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setFeedback("");
    try {
      const data = await updateAzureMonitoringSchedule(subscription, {
        enabled, interval_minutes: Number(interval), include_security: includeSecurity,
      });
      setSchedule(data);
      setEnabled(data.enabled);
      setIncludeSecurity(data.include_security ?? false);
      setInterval(String(data.interval_minutes));
      setFeedback("Schedule saved.");
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  return <section className="card account-form">
    <h2>Collection schedule</h2>
    <p>Collect monitoring and network snapshots for this subscription from the latest complete Azure inventory.</p>
    {error && <div className="error" role="alert">{error}</div>}
    {feedback && <p role="status">{feedback}</p>}
    {!schedule && !error && <p role="status">Loading schedule…</p>}
    {schedule && <form onSubmit={save}>
      <fieldset disabled={busy}>
        <label className="observability-checkbox"><input type="checkbox" checked={enabled}
          onChange={(event) => setEnabled(event.target.checked)} /> Enable scheduled collection</label>
        <label className="observability-checkbox"><input type="checkbox" checked={includeSecurity}
          onChange={(event) => setIncludeSecurity(event.target.checked)} /> Include security posture and threats</label>
        <label>Interval (minutes)<input type="number" min={5} max={1440} step={1} value={interval} required
          onChange={(event) => setInterval(event.target.value)} /></label>
        {schedule.enabled && <p>Next scheduled collection {snapshotTime(schedule.next_run_at)}</p>}
        <div><button type="submit">{busy ? "Saving…" : "Save schedule"}</button></div>
      </fieldset>
    </form>}
  </section>;
}

export default function AzureMonitoringWorkspace({ canRefresh, canManageSchedule }) {
  const [showDiagnostics, setShowDiagnostics] = useState(false);

  return <AzureSnapshotWorkspace title="Infrastructure Monitoring"
    description="Review Azure availability and recent metrics for resources in the selected subscription."
    canRefresh={canRefresh} loadSnapshot={getAzureMonitoring} refreshSnapshot={refreshAzureMonitoring}>
    {(snapshot, subscription) => <>
      {canManageSchedule && <MonitoringSchedule subscription={subscription} />}
      {snapshot && <MonitoringResources snapshot={snapshot} />}
      {canRefresh && <>
        <div className="actions">
          <button type="button" aria-expanded={showDiagnostics}
            onClick={() => setShowDiagnostics((visible) => !visible)}>
            {showDiagnostics ? "Hide advanced diagnostics" : "Open advanced diagnostics"}
          </button>
        </div>
        {showDiagnostics && <AzureDiagnostics subscription={subscription} />}
      </>}
    </>}
  </AzureSnapshotWorkspace>;
}
