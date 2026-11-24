import { useEffect, useState } from "react";
import { getAzureConnectionStatus, getAzureInventory, getAzureMonitoring, getAzureSecurity, getAzureHealthIncidents, getComplianceReviews } from "../services/api";
import { displayLabel, snapshotTime } from "./AzureSnapshotWorkspace";

const SOURCES = [
  ["inventory", "Inventory", getAzureInventory],
  ["monitoring", "Monitoring", getAzureMonitoring],
  ["security", "Security", getAzureSecurity],
  ["incidents", "Incidents", (subscription) => getAzureHealthIncidents(subscription, 1)],
  ["compliance", "Compliance", getComplianceReviews],
];

function getSummary(snapshots) {
  const { inventory, monitoring, security, incidents, compliance } = snapshots;
  const resources = monitoring?.resources || [];
  const confirmed = resources.filter(({ health_status, health }) =>
    health_status === "synced" && ["available", "degraded", "unavailable"].includes(health));
  const issues = confirmed.filter(({ health }) => health !== "available");
  return [
    ["Inventoried resources", inventory?.last_success_at ? inventory.resources.length : null, "inventory"],
    ["Confirmed health coverage", confirmed.length ? `${confirmed.length} of ${resources.length}` : null, "monitoring"],
    ["Degraded or unavailable", confirmed.length ? issues.length : null, "monitoring"],
    ["Acknowledged health findings", confirmed.length ? issues.filter(({ health_alert }) => health_alert?.acknowledged_at).length : null, "monitoring"],
    ["Security findings", security?.last_success_at || security?.findings?.length ? security.findings.length : null, "security"],
    ["Security risk score", Number.isFinite(security?.score) ? security.score : null, "security"],
    ["Open or investigating incidents on first page", incidents?.incidents?.filter(({ status }) => status !== "resolved").length ?? null, "incidents"],
    ["Compliance reviews requiring action", Array.isArray(compliance) ? compliance.filter(({ state }) => state === "action_required").length : null, "compliance"],
  ];
}

function dueState(dueDate) {
  if (!dueDate) return "Unscheduled";
  const end = new Date(`${dueDate}T23:59:59`);
  return Number.isFinite(end.getTime()) && end < new Date() ? `Overdue · ${dueDate}` : `Due ${dueDate}`;
}

export function getPriorities(snapshots) {
  const priorities = [];
  const add = (priority) => priorities.push({ owner: "Unassigned", due: null, ...priority });
  for (const [key, label] of [["inventory", "Inventory"], ["monitoring", "Monitoring"], ["security", "Security"]]) {
    const snapshot = snapshots[key];
    if (!snapshot) {
      add({ id: `${key}-unavailable`, title: `${label} evidence could not be loaded`, source: label,
        freshness: "Unavailable", impact: "Operational visibility is incomplete", workspace: key });
    } else if (snapshot.status && snapshot.status !== "synced") {
      add({ id: `${key}-${snapshot.status}`, title: `${label} collection requires attention`, source: label,
        freshness: snapshot.last_success_at ? `Retained from ${snapshotTime(snapshot.last_success_at)}` : "No complete evidence",
        impact: displayLabel(snapshot.status), workspace: key });
    }
  }

  const incidents = snapshots.incidents?.incidents || [];
  const incidentResources = new Set(incidents.filter(({ status }) => status !== "resolved").map(({ resource_id }) => resource_id));
  for (const resource of snapshots.monitoring?.resources || []) {
    if (resource.health_status === "synced" && ["degraded", "unavailable"].includes(resource.health)
        && !incidentResources.has(resource.id)) {
      add({ id: `health-${resource.id}`, title: `${resource.name || resource.id} is ${resource.health}`,
        source: "Azure Resource Health", freshness: snapshotTime(snapshots.monitoring.last_success_at),
        impact: resource.health === "unavailable" ? "Service unavailable" : "Service degraded", workspace: "monitoring" });
    }
  }
  for (const incident of incidents.filter(({ status }) => status !== "resolved")) {
    add({ id: `incident-${incident.id}`, title: `Investigate ${incident.resource_id}`,
      source: "Health incident", freshness: snapshotTime(incident.collected_at), impact: displayLabel(incident.health),
      owner: incident.owner || "Unassigned", workspace: "monitoring" });
  }
  for (const finding of snapshots.security?.findings || []) {
    const tracking = finding.tracking;
    if (!tracking || !["resolved", "accepted"].includes(tracking.status)) {
      add({ id: `security-${finding.id}`, title: finding.title || "Security finding requires review",
        source: finding.source || "Security evidence", freshness: snapshotTime(finding.observed_at || snapshots.security.last_success_at),
        impact: displayLabel(finding.severity || "Review required"), owner: tracking?.owner || "Unassigned",
        due: tracking?.due_date || null, workspace: "security" });
    }
  }
  for (const review of Array.isArray(snapshots.compliance) ? snapshots.compliance : []) {
    if (review.state === "action_required" || (review.action && review.action_status !== "completed")) {
      add({ id: `compliance-${review.topic}`, title: review.action || `${displayLabel(review.topic)} review requires action`,
        source: "Compliance review", freshness: snapshotTime(review.evidence_at || review.updated_at),
        impact: displayLabel(review.state), owner: review.owner || "Unassigned", due: review.due_date || null,
        workspace: "compliance" });
    }
  }
  return priorities.sort((left, right) => {
    const leftOverdue = dueState(left.due).startsWith("Overdue") ? 0 : 1;
    const rightOverdue = dueState(right.due).startsWith("Overdue") ? 0 : 1;
    return leftOverdue - rightOverdue || left.title.localeCompare(right.title);
  });
}

function downloadSummary(clientName, subscription, snapshots, metrics) {
  const report = {
    client: clientName, subscription, generated_at: new Date().toISOString(),
    summary: Object.fromEntries(metrics.map(([label, value]) => [label, value])),
    sources: Object.fromEntries(SOURCES.map(([key]) => {
      const snapshot = snapshots[key];
      return [key, {
        status: snapshot?.status ?? (snapshot ? "records_available" : "unavailable"),
        last_complete_collection: snapshot?.last_success_at ?? null,
        limitations: snapshot?.limitations ?? (key === "incidents" && snapshot?.has_next ? ["Overview includes the first page of incidents."] : []),
      }];
    })),
  };
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "monitorai-subscription-summary.json";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function SubscriptionDashboard({ clientName, subscription, onOpen }) {
  const [snapshots, setSnapshots] = useState(null);
  useEffect(() => {
    let active = true;
    Promise.allSettled(SOURCES.map(([, , load]) => load(subscription))).then((results) => {
      if (active) setSnapshots(Object.fromEntries(SOURCES.map(([key], index) => [
        key, results[index].status === "fulfilled" ? results[index].value : null,
      ])));
    });
    return () => { active = false; };
  }, [subscription]);

  if (!snapshots) return <p role="status">Loading saved subscription evidence...</p>;

  const metrics = getSummary(snapshots);
  const priorities = getPriorities(snapshots);
  return <>
    <section className="card account-form">
      <h2>Priority work queue</h2>
      <p>Priorities below come only from saved collection, finding, incident, and compliance evidence.</p>
      {priorities.length ? <div className="design-table"><table className="table" aria-label="Evidence-backed priorities">
        <thead><tr><th scope="col">Priority</th><th scope="col">Evidence</th><th scope="col">Impact</th><th scope="col">Ownership</th><th scope="col">Action</th></tr></thead>
        <tbody>{priorities.map((priority) => <tr key={priority.id}>
          <td>{priority.title}</td>
          <td>{priority.source}<br /><small>{priority.freshness}</small></td>
          <td>{priority.impact}</td>
          <td>{priority.owner}<br /><small>{dueState(priority.due)}</small></td>
          <td><button type="button" onClick={() => onOpen(priority.workspace)}>Open {displayLabel(priority.workspace)}</button></td>
        </tr>)}</tbody>
      </table></div> : <p>No evidence-backed priorities are currently recorded.</p>}
    </section>
    <div className="platform-grid">
      {metrics.map(([label, value, key]) => (
        <article className="platform-card" key={label}>
          <h3>{label}</h3>
          <div className="platform-value">{value ?? "Unavailable"}</div>
          <p>{displayLabel(snapshots[key]?.status || (snapshots[key] ? "Saved records" : "Unavailable"))}</p>
        </article>
      ))}
    </div>
    <section className="card account-form">
      <h2>Evidence status</h2>
      {SOURCES.map(([key, label]) => {
        const snapshot = snapshots[key];
        return <div key={key}>
          <button type="button" className="dismiss" onClick={() => onOpen(key === "incidents" ? "monitoring" : key)}>{label}</button>
          {snapshot?.status && <p>{displayLabel(snapshot.status)} | Last complete collection {snapshotTime(snapshot.last_success_at)}</p>}
          {!snapshot && <p>Saved evidence could not be loaded.</p>}
          {key === "incidents" && snapshot?.has_next && <p>Overview includes the first page of incidents.</p>}
          {snapshot?.limitations?.length > 0 && <ul>{snapshot.limitations.map((limit, index) => <li key={index}>{limit}</li>)}</ul>}
        </div>;
      })}
      <div><button type="button" onClick={() => downloadSummary(clientName, subscription, snapshots, metrics)}>
        Download subscription summary
      </button></div>
    </section>
  </>;
}

export default function PlatformDashboard({ clientName, onOpen }) {
  const [connection, setConnection] = useState(null);
  const [error, setError] = useState("");
  const [choice, setChoice] = useState("");
  useEffect(() => {
    let active = true;
    getAzureConnectionStatus().then((result) => {
      if (active) setConnection(result);
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") setError(failure.message);
    });
    return () => { active = false; };
  }, []);

  const subscriptions = connection?.configured_subscription_ids || [];
  const subscription = subscriptions.includes(choice) ? choice : subscriptions[0];

  return <section className="workspace-panel azure-observability">
    <div className="workspace-header"><div><h1>Overview</h1><p>{clientName}</p></div></div>
    <section className="card account-form">
      <h2>Client overview</h2>
      {error && <p className="error" role="alert">{error}</p>}
      {!connection && !error && <p role="status">Loading Azure subscriptions...</p>}
      {connection && !subscription && <div>
        <p>Configure an Azure subscription to review its saved evidence.</p>
        <button type="button" onClick={() => onOpen("azure")}>Open Azure Connection</button>
      </div>}
      {subscription && <label>Subscription<select value={subscription} onChange={(event) => setChoice(event.target.value)}>
        {subscriptions.map((id) => <option key={id} value={id}>{id}</option>)}
      </select></label>}
    </section>
    {subscription && <SubscriptionDashboard key={subscription} clientName={clientName} subscription={subscription} onOpen={onOpen} />}
  </section>;
}
