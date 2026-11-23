import { useEffect, useState } from "react";
import { getAzureConnectionStatus, getAzureInventory, getAzureMonitoring, getAzureSecurity } from "../services/api";
import { displayLabel, snapshotTime } from "./AzureSnapshotWorkspace";

const SOURCES = [
  ["inventory", "Inventory", getAzureInventory],
  ["monitoring", "Monitoring", getAzureMonitoring],
  ["security", "Security", getAzureSecurity],
];

function getSummary(snapshots) {
  const { inventory, monitoring, security } = snapshots;
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
  ];
}

function downloadSummary(clientName, subscription, snapshots, metrics) {
  const report = {
    client: clientName, subscription, generated_at: new Date().toISOString(),
    summary: Object.fromEntries(metrics.map(([label, value]) => [label, value])),
    sources: Object.fromEntries(SOURCES.map(([key]) => {
      const snapshot = snapshots[key];
      return [key, {
        status: snapshot?.status ?? "unavailable",
        last_complete_collection: snapshot?.last_success_at ?? null,
        limitations: snapshot?.limitations ?? [],
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
  return <>
    <div className="platform-grid">
      {metrics.map(([label, value, key]) => (
        <article className="platform-card" key={label}>
          <h3>{label}</h3>
          <div className="platform-value">{value ?? "Unavailable"}</div>
          <p>{displayLabel(snapshots[key]?.status)}</p>
        </article>
      ))}
    </div>
    <section className="card account-form">
      <h2>Evidence status</h2>
      {SOURCES.map(([key, label]) => {
        const snapshot = snapshots[key];
        return <div key={key}>
          <button type="button" className="dismiss" onClick={() => onOpen(key)}>{label}</button>
          <p>{snapshot ? `${displayLabel(snapshot.status)} | Last complete collection ${snapshotTime(snapshot.last_success_at)}` : "Saved evidence could not be loaded."}</p>
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
