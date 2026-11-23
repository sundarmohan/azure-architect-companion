import { useEffect, useState } from "react";
import {
  getAzureConnectionStatus, getAzureHealthIncidents, getAzureInventory, getAzureMonitoring,
  getAzureSecurity, getComplianceReviews,
} from "../services/api";
import { displayLabel, snapshotTime } from "./AzureSnapshotWorkspace";

const ROW_LIMIT = 20;
const SOURCES = {
  inventory: {
    label: "Azure Inventory", load: getAzureInventory,
    rows: (data) => (data.resources || []).slice(0, ROW_LIMIT).map(({ id, type, location }) => ({ id, type, location })),
    count: (data) => (data.resources || []).length,
  },
  monitoring: {
    label: "Azure Resource Health and monitoring", load: getAzureMonitoring,
    rows: (data) => (data.resources || []).slice(0, ROW_LIMIT).map(({ id, health, health_status, metrics_status }) =>
      ({ id, health, health_status, metrics_status })),
    count: (data) => (data.resources || []).length,
  },
  security: {
    label: "Azure Security findings", load: getAzureSecurity,
    rows: (data) => (data.findings || []).slice(0, ROW_LIMIT).map(({ code, source, severity, resource_id, observed_at, tracking }) =>
      ({ code, source, severity, resource_id, observed_at, tracking_status: tracking?.status })),
    count: (data) => (data.findings || []).length,
  },
  compliance: {
    label: "MonitorAI compliance reviews", load: getComplianceReviews,
    rows: (data) => data.slice(0, ROW_LIMIT).map(({ topic, state, action_status, due_date, evidence_at, updated_at }) =>
      ({ topic, state, action_status, due_date, evidence_at, updated_at })),
    count: (data) => data.length,
  },
  incidents: {
    label: "MonitorAI health incidents", load: (subscription) => getAzureHealthIncidents(subscription, 1),
    rows: (data) => (data.incidents || []).slice(0, ROW_LIMIT).map(({ id, resource_id, health, status, collected_at, updated_at }) =>
      ({ id, resource_id, health, status, collected_at, updated_at })),
    count: (data) => (data.incidents || []).length,
  },
};

const REPORTS = {
  technical: ["inventory", "monitoring", "incidents"],
  security: ["security"],
  compliance: ["compliance", "security"],
  executive: ["inventory", "monitoring", "security", "compliance", "incidents"],
};

function downloadJson(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export default function ReportsWorkspace() {
  const [subscriptions, setSubscriptions] = useState(null);
  const [subscription, setSubscription] = useState("");
  const [type, setType] = useState("technical");
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    getAzureConnectionStatus().then((connection) => {
      if (!active) return;
      const configured = connection.configured_subscription_ids?.length
        ? connection.configured_subscription_ids
        : (connection.configured_subscription_id ? [connection.configured_subscription_id] : []);
      setSubscriptions(configured);
      setSubscription(configured[0] || "");
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") setError("Configured Azure subscriptions could not be loaded.");
    });
    return () => { active = false; };
  }, []);

  async function generate(event) {
    event.preventDefault();
    if (!subscription || busy) return;
    setBusy(true);
    setReport(null);
    const result = await Promise.allSettled(REPORTS[type].map((key) => SOURCES[key].load(subscription)));
    if (!result.some((entry) => entry.status === "rejected" && entry.reason?.name === "AbortError")) {
      const sources = result.map((entry, index) => {
        const key = REPORTS[type][index];
        const projection = SOURCES[key];
        const origin = { source: key, label: projection.label };
        if (entry.status === "rejected") return { ...origin, status: "unavailable" };
        const data = entry.value;
        const rows = projection.rows(data);
        const count = projection.count(data);
        return {
          ...origin,
          status: data.status || "loaded",
          last_attempt_at: data.last_attempt_at || null,
          last_complete_at: data.last_success_at || null,
          count,
          truncated: Boolean(data.has_next) || rows.length < count,
          ...(key === "security" && { risk_score: data.score ?? null }),
          rows,
        };
      });
      setReport({ type, subscription_id: subscription, generated_at: new Date().toISOString(), sources });
    }
    setBusy(false);
  }

  return <section className="workspace-panel azure-observability">
    <header className="workspace-header"><div><h1>Reports</h1></div></header>
    <section className="card account-form">
      <h2>Subscription evidence report</h2>
      <p>Reports summarize saved evidence and the first 20 detail records from each source. Source status and collection time indicate coverage.</p>
      {error && <p role="alert" className="error">{error}</p>}
      {!subscriptions && !error && <p role="status">Loading subscriptions…</p>}
      {subscriptions?.length === 0 && <p>Configure an Azure subscription to generate reports.</p>}
      {Boolean(subscriptions?.length) && <form className="account-form" onSubmit={generate}>
        <fieldset disabled={busy}>
          <label>Subscription<select value={subscription} onChange={(event) => {
            setReport(null);
            setSubscription(event.target.value);
          }}>{subscriptions.map((id) => <option key={id}>{id}</option>)}</select></label>
          <label>Report type<select value={type} onChange={(event) => {
            setReport(null);
            setType(event.target.value);
          }}>{Object.keys(REPORTS).map((key) => <option key={key} value={key}>{displayLabel(key)}</option>)}</select></label>
          <button type="submit">Generate report</button>
        </fieldset>
      </form>}
      {busy && <p role="status">Reading report evidence…</p>}
      {report && <>
        <h3>{displayLabel(report.type)} report</h3>
        <p>Generated {snapshotTime(report.generated_at)}</p>
        <ul className="design-list">{report.sources.map((source) => <li key={source.source}>
          <strong>{source.label}</strong>
          <span>{displayLabel(source.status)}{source.count != null && ` · ${source.count} records read`}</span>
          {source.last_complete_at && <span>Last complete collection {snapshotTime(source.last_complete_at)}</span>}
          {source.last_attempt_at && <span>Last collection attempt {snapshotTime(source.last_attempt_at)}</span>}
          {source.risk_score != null && <span>Saved risk score {source.risk_score}</span>}
          {source.truncated && <span>Detail records are limited in this report.</span>}
        </li>)}</ul>
        <div><button type="button" onClick={() => downloadJson(`monitorai-${report.type}-report.json`, report)}>
          Download JSON
        </button></div>
      </>}
    </section>
  </section>;
}
