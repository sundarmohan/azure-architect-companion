import { useEffect, useState } from "react";
import { getAzureConnectionStatus } from "../services/api";

const SNAPSHOT_STATUS = {
  not_configured: "Configure an Azure connection for this client.",
  not_synced: "This subscription has no snapshot yet.",
  inventory_required: "Refresh Azure Inventory for this subscription before collecting a snapshot.",
  synced: "Snapshot collected successfully.",
  authentication_failure: "Azure authentication failed.",
  permission_failure: "The Azure connection lacks permission to collect this data.",
  provider_error: "Azure did not return a complete snapshot.",
  partial_failure: "Some Azure data could not be collected.",
};

export function displayLabel(value) {
  return String(value || "Unknown").replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

export function snapshotTime(value) {
  const date = new Date(value);
  return value && Number.isFinite(date.getTime()) ? date.toLocaleString() : "Never";
}

function SnapshotPanel({ subscription, canRefresh, loadSnapshot, refreshSnapshot, children }) {
  const [snapshot, setSnapshot] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    loadSnapshot(subscription).then((data) => {
      if (active) setSnapshot(data);
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") setError(failure.message);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [loadSnapshot, subscription]);

  async function refresh() {
    setRefreshing(true);
    setError("");
    try {
      setSnapshot(await refreshSnapshot(subscription));
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setRefreshing(false);
    }
  }

  return <>
    <section className="card account-form">
      <h2>Collection status</h2>
      {error && <div className="error" role="alert">{error}</div>}
      {loading && <p role="status">Loading subscription snapshot…</p>}
      {snapshot && <>
        <p role="status">{SNAPSHOT_STATUS[snapshot.status] || displayLabel(snapshot.status)}</p>
        {snapshot.failure_reason && snapshot.failure_reason !== snapshot.status && <p>{SNAPSHOT_STATUS[snapshot.failure_reason] || displayLabel(snapshot.failure_reason)}</p>}
        <p>Last attempt {snapshotTime(snapshot.last_attempt_at)} · Last successful collection {snapshotTime(snapshot.last_success_at)}</p>
        {snapshot.last_success_at && snapshot.status !== "synced" && <p>Showing the last available data.</p>}
      </>}
      {canRefresh && <div><button disabled={loading || refreshing} onClick={refresh}>
        {refreshing ? "Refreshing…" : "Refresh snapshot"}
      </button></div>}
    </section>
    {children(snapshot, subscription)}
  </>;
}

export default function AzureSnapshotWorkspace({ title, description, canRefresh, loadSnapshot, refreshSnapshot, children }) {
  const [connection, setConnection] = useState(null);
  const [subscription, setSubscription] = useState("");
  const [error, setError] = useState("");
  const subscriptions = connection?.configured_subscription_ids?.length
    ? connection.configured_subscription_ids
    : (connection?.configured_subscription_id ? [connection.configured_subscription_id] : []);

  useEffect(() => {
    let active = true;
    getAzureConnectionStatus().then((status) => {
      if (!active) return;
      setConnection(status);
      setSubscription(status.configured_subscription_id || status.configured_subscription_ids?.[0] || "");
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") setError(failure.message);
    });
    return () => { active = false; };
  }, []);

  return <section className="workspace-panel azure-observability">
    <div className="workspace-header"><div>
      <h1>{title}</h1>
      <p>{description}</p>
    </div></div>
    {error && <div className="error" role="alert">{error}</div>}
    {!connection && !error && <p role="status">Loading Azure connections…</p>}
    {connection && !subscriptions.length && <p>{SNAPSHOT_STATUS.not_configured}</p>}
    {subscription && <>
      <div className="card account-form">
        <label>Subscription<select value={subscription} onChange={(event) => setSubscription(event.target.value)}>
          {subscriptions.map((id) => <option key={id} value={id}>{id}</option>)}
        </select></label>
      </div>
      <SnapshotPanel key={subscription} subscription={subscription} canRefresh={canRefresh} loadSnapshot={loadSnapshot} refreshSnapshot={refreshSnapshot}>
        {children}
      </SnapshotPanel>
    </>}
  </section>;
}
