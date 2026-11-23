import { useState } from "react";
import { getAzureSecurity, refreshAzureSecurity, updateAzureFindingTracking } from "../services/api";
import AzureSnapshotWorkspace, { displayLabel, snapshotTime } from "./AzureSnapshotWorkspace";

const SEVERITIES = ["critical", "high", "medium", "low", "informational"];
const PAGE_SIZE = 20;
const NUMBER_FORMAT = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const TRACKING_STATUSES = ["open", "in_progress", "resolved", "accepted"];
const TRACKING_ID = /^[a-f0-9]{64}$/;

function severityRank(severity) {
  const rank = SEVERITIES.indexOf(severity?.toLowerCase());
  return rank === -1 ? SEVERITIES.length : rank;
}

function FindingEvidence({ evidence }) {
  if (!evidence?.length) return <p>No evidence supplied.</p>;
  return <ul>{evidence.map((text, index) => <li key={index}>{text}</li>)}</ul>;
}

function FindingTracking({ finding, subscription, canEdit, onSave, onSaveStart }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { status = "open", owner, due_date } = finding.tracking || {};

  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    onSaveStart();
    const fields = new FormData(event.currentTarget);
    try {
      const saved = await updateAzureFindingTracking(subscription, finding.id, {
        status: fields.get("status"),
        owner: fields.get("owner").trim() || null,
        due_date: fields.get("due_date") || null,
      });
      onSave(finding.id, saved);
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  return <details>
    <summary>Remediation tracking · {displayLabel(status)}</summary>
    {finding.tracking ? <dl className="design-meta">
      <div><dt>Owner</dt><dd>{owner || "Unassigned"}</dd></div>
      <div><dt>Due date</dt><dd>{due_date || "None"}</dd></div>
    </dl> : <p>No tracking record yet.</p>}
    {canEdit && <form className="account-form" key={JSON.stringify([status, owner, due_date])} onSubmit={save}>
      <fieldset disabled={busy}>
        <label>Status<select name="status" defaultValue={status}>
          {TRACKING_STATUSES.map((value) => <option key={value} value={value}>{displayLabel(value)}</option>)}
        </select></label>
        <label>Owner<input name="owner" defaultValue={owner || ""} /></label>
        <label>Due date<input name="due_date" type="date" defaultValue={due_date || ""} /></label>
        <div><button type="submit">{busy ? "Saving…" : "Save tracking"}</button></div>
      </fieldset>
    </form>}
    {error && <p role="alert" className="error">{error}</p>}
  </details>;
}

export function correlateThreatEvidence(findings, subscriptionId) {
  if (!subscriptionId) return [];
  const prefix = `/subscriptions/${subscriptionId.toLowerCase()}/resourcegroups/`;
  const byResource = new Map();
  for (const item of findings) {
    const key = item.resource_id?.toLowerCase();
    if (!key?.startsWith(prefix)) continue;
    const isDefenderAlert = item.source === "azure_defender_alerts" && item.code === "defender_active_alerts";
    const isActivitySignal = item.source === "azure_activity_rule" && item.code === "repeated_security_control_failures";
    if (!isDefenderAlert && !isActivitySignal) continue;
    if (!byResource.has(key)) byResource.set(key, { resource: item.resource_id, alerts: [], activity: [] });
    const group = byResource.get(key);
    (isDefenderAlert ? group.alerts : group.activity).push(item);
  }
  return [...byResource.values()].filter(({ alerts, activity }) => alerts.length && activity.length);
}

function ThreatEvidence({ findings, snapshot, subscription, onReview }) {
  const groups = correlateThreatEvidence(findings, subscription);
  if (!groups.length) return null;
  return <section className="card account-form">
    <h2>Correlated threat evidence</h2>
    <p>Saved Defender alerts and repeated failed security changes share these resource IDs. Review the source records to establish timing and cause.</p>
    {snapshot.status !== "synced" && <p>{snapshot.last_success_at
      ? "Correlation uses retained evidence from the last complete collection."
      : "Correlation uses incomplete evidence."}</p>}
    <ul className="design-list">
      {groups.map(({ resource, alerts, activity }) => <li key={resource.toLowerCase()}>
        <strong>{resource}</strong>
        <span>{alerts.length} Defender alert groups | {activity.length} Azure Activity signals</span>
        <details><summary>Matched evidence</summary>
          <ul>{[...alerts, ...activity].map((item) => <li key={item.id}>
            <strong>{item.title}</strong>
            <span>{displayLabel(item.source)}{item.observed_at && ` | Collected ${snapshotTime(item.observed_at)}`}</span>
            <FindingEvidence evidence={item.evidence} />
          </li>)}</ul>
        </details>
        <div><button type="button" onClick={() => onReview(resource)}>Filter findings for this resource</button></div>
      </li>)}
    </ul>
  </section>;
}

function SecurityFindings({ snapshot, subscription, canEdit, onSaveTracking }) {
  const [severity, setSeverity] = useState("");
  const [source, setSource] = useState("");
  const [category, setCategory] = useState("");
  const [filter, setFilter] = useState("");
  const [trackingStatus, setTrackingStatus] = useState("");
  const [attention, setAttention] = useState("");
  const [trackingSaved, setTrackingSaved] = useState(false);
  const [page, setPage] = useState(0);
  const findings = snapshot.findings || [];
  const score = snapshot.score;
  const sources = [...new Set(findings.map((item) => item.source).filter(Boolean))].sort();
  const categories = [...new Set(findings.map((item) => item.category).filter(Boolean))].sort();
  const severities = [...new Set(findings.map((item) => item.severity).filter(Boolean))]
    .sort((left, right) => severityRank(left) - severityRank(right));
  const activeSeverity = severities.includes(severity) ? severity : "";
  const activeSource = sources.includes(source) ? source : "";
  const activeCategory = categories.includes(category) ? category : "";
  const search = filter.trim().toLowerCase();
  const today = new Date();
  const localDate = [today.getFullYear(), today.getMonth() + 1, today.getDate()]
    .map((part) => String(part).padStart(2, "0")).join("-");
  const triage = findings.map((item) => {
    const status = TRACKING_ID.test(item.id || "") ? item.tracking?.status || "open" : null;
    const outstanding = status === "open" || status === "in_progress";
    return {
      item,
      status,
      outstanding,
      overdue: outstanding && Boolean(item.tracking?.due_date && item.tracking.due_date < localDate),
      unassigned: outstanding && !item.tracking?.owner?.trim(),
    };
  });
  const matching = triage.filter(({ item, status, overdue, unassigned }) => (
    (!activeSeverity || item.severity === activeSeverity) &&
    (!activeSource || item.source === activeSource) &&
    (!activeCategory || item.category === activeCategory) &&
    (!trackingStatus || status === trackingStatus) &&
    (attention !== "overdue" || overdue) &&
    (attention !== "unassigned" || unassigned) &&
    (!search || [item.code, item.title, item.resource_id].some((value) => value?.toLowerCase().includes(search)))
  )).sort((left, right) => severityRank(left.item.severity) - severityRank(right.item.severity));
  const pageCount = Math.ceil(matching.length / PAGE_SIZE);
  const currentPage = Math.min(page, Math.max(0, pageCount - 1));

  return <>
    <section className="card account-form">
      <h2>Security posture</h2>
      <p>Risk score <strong>{Number.isFinite(score) ? `${NUMBER_FORMAT.format(score)} / 100` : "Unavailable"}</strong></p>
      <p>Higher scores indicate greater risk.</p>
      {snapshot.score_factors?.length > 0 && <details>
        <summary>Score factors</summary>
        <div className="design-table"><table className="table">
          <thead><tr><th scope="col">Severity</th><th scope="col">Findings</th><th scope="col">Weight per finding</th></tr></thead>
          <tbody>{snapshot.score_factors.map(({ severity: level, count, weight }) => (
            <tr key={level}><td>{displayLabel(level)}</td><td>{count}</td><td>{weight}</td></tr>
          ))}</tbody>
        </table></div>
      </details>}
      {snapshot.limitations?.length > 0 && <>
        <h3>Coverage and limitations</h3>
        <ul>{snapshot.limitations.map((text) => <li key={text}>{text}</li>)}</ul>
      </>}
    </section>
    <ThreatEvidence findings={findings} snapshot={snapshot} subscription={subscription} onReview={(resource) => {
      setFilter(resource);
      setSeverity("");
      setSource("");
      setCategory("");
      setTrackingStatus("");
      setAttention("");
      setPage(0);
    }} />
    <section className="card account-form">
      <h2>Findings ({findings.length})</h2>
      {trackingSaved && <p role="status">Remediation tracking saved.</p>}
      {findings.length > 0 && <>
        <p>Tracking reflects local remediation decisions for the findings in this snapshot. Azure evidence is reviewed separately.</p>
        <p>Outstanding {triage.filter((row) => row.outstanding).length} · Overdue {triage.filter((row) => row.overdue).length} · Unassigned {triage.filter((row) => row.unassigned).length}</p>
        {snapshot.status !== "synced" && <p>{snapshot.last_success_at
          ? "Triage is based on retained findings from the last complete collection."
          : "Triage is based on incomplete Azure evidence."}</p>}
      </>}
      {findings.length > 0 && <div className="grid">
        <label>Filter findings<input value={filter} placeholder="Title, code, or Azure resource ID"
          onChange={(event) => { setFilter(event.target.value); setPage(0); }} /></label>
        <label>Severity<select value={activeSeverity} onChange={(event) => { setSeverity(event.target.value); setPage(0); }}>
          <option value="">All severities</option>
          {severities.map((value) => <option key={value} value={value}>{displayLabel(value)}</option>)}
        </select></label>
        <label>Source<select value={activeSource} onChange={(event) => { setSource(event.target.value); setPage(0); }}>
          <option value="">All sources</option>
          {sources.map((value) => <option key={value} value={value}>{displayLabel(value)}</option>)}
        </select></label>
        {categories.length > 0 && <label>Category<select value={activeCategory} onChange={(event) => { setCategory(event.target.value); setPage(0); }}>
          <option value="">All categories</option>
          {categories.map((value) => <option key={value} value={value}>{displayLabel(value)}</option>)}
        </select></label>}
        <label>Tracking status<select value={trackingStatus} onChange={(event) => { setTrackingStatus(event.target.value); setPage(0); }}>
          <option value="">All tracking statuses</option>
          {TRACKING_STATUSES.map((value) => <option key={value} value={value}>{displayLabel(value)}</option>)}
        </select></label>
        <label>Needs attention<select value={attention} onChange={(event) => { setAttention(event.target.value); setPage(0); }}>
          <option value="">Any</option>
          <option value="overdue">Overdue</option>
          <option value="unassigned">Unassigned</option>
        </select></label>
      </div>}
      {matching.length > 0 ? <ul className="design-list">
        {matching.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE).map(({ item, status, overdue, unassigned }, index) => (
          <li key={item.id || `${item.source}-${item.code}-${item.resource_id}-${index}`}>
            <strong>{item.title}</strong>
            <span>{displayLabel(item.severity)} · {displayLabel(item.source)} · {item.code}</span>
            {(item.category || item.observed_at) && <span>{[
              item.category && displayLabel(item.category),
              item.observed_at && `Observed ${snapshotTime(item.observed_at)}`,
            ].filter(Boolean).join(" · ")}</span>}
            {item.resource_id && <span>Resource {item.resource_id}</span>}
            {item.recommendation && <p>{item.recommendation}</p>}
            {(overdue || unassigned) && <span>{[overdue && "Overdue", unassigned && "Unassigned"].filter(Boolean).join(" · ")}</span>}
            <details><summary>Evidence</summary><FindingEvidence evidence={item.evidence} /></details>
            {item.incident_links?.length > 0 && <details>
              <summary>Related incidents ({item.incident_links.length})</summary>
              <ul>{item.incident_links.map((incident) => <li key={incident.id}>
                <strong>Incident {incident.id}</strong>
                <span>{displayLabel(incident.status)} · Owner {incident.owner || "Unassigned"} · Linked {snapshotTime(incident.linked_at)}</span>
              </li>)}</ul>
            </details>}
            {status && <FindingTracking finding={item}
              subscription={subscription} canEdit={canEdit} onSaveStart={() => setTrackingSaved(false)}
              onSave={(id, tracking) => {
                onSaveTracking(id, tracking);
                setTrackingSaved(true);
              }} />}
          </li>
        ))}
      </ul> : <p>{findings.length ? "No findings match the filters." : "No findings in the current snapshot."}</p>}
      {pageCount > 1 && <div className="actions">
        <button type="button" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous</button>
        <span aria-live="polite">Page {currentPage + 1} of {pageCount}</span>
        <button type="button" disabled={currentPage + 1 === pageCount} onClick={() => setPage(currentPage + 1)}>Next</button>
      </div>}
    </section>
  </>;
}

export default function AzureSecurityWorkspace({ canRefresh }) {
  return <AzureSnapshotWorkspace title="Azure Security Posture and Threats"
    description="Review security findings and their evidence for the selected Azure subscription."
    canRefresh={canRefresh} loadSnapshot={getAzureSecurity} refreshSnapshot={refreshAzureSecurity}>
    {(snapshot, subscription, setSnapshot) => snapshot && <SecurityFindings
      snapshot={snapshot} subscription={subscription} canEdit={canRefresh}
      onSaveTracking={(id, tracking) => setSnapshot((current) => current && ({
        ...current,
        findings: current.findings.map((finding) => finding.id === id ? { ...finding, tracking } : finding),
      }))} />}
  </AzureSnapshotWorkspace>;
}
