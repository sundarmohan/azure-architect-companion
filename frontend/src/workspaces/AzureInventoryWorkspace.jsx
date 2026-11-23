import { useEffect, useMemo, useState } from "react";
import { getAzureConnectionStatus, getAzureInventory, refreshAzureInventory } from "../services/api";

const STATUS_TEXT = {
  not_configured: "Configure an Azure connection to collect inventory.",
  not_synced: "This subscription has no inventory snapshot yet.",
  synced: "Inventory refreshed successfully.",
  authentication_failure: "Azure authentication failed.",
  permission_failure: "The Azure connection lacks permission to read this inventory.",
  provider_error: "Azure could not return inventory. Previously collected data remains visible.",
  partial_failure: "Azure returned an incomplete result. Any previous complete snapshot remains visible.",
};

const FAILURE_ACTION = {
  credential_rejected: "Review the Azure credentials and test the connection before refreshing again.",
  insufficient_permission: "Grant Reader access for this subscription and refresh again.",
  authentication_failure: "Test the Azure connection and update rejected credentials.",
  permission_failure: "Grant the service principal permission to list the failed inventory scope.",
  throttled: "Azure throttled collection. Wait before refreshing again.",
  timeout: "Azure did not respond in time. Check connectivity and retry.",
  network_error: "Check outbound access to management.azure.com and retry.",
  invalid_response: "Azure returned an invalid inventory response. Retry and use the support reference if it repeats.",
  provider_error: "Retry collection. If it repeats, use the support reference.",
};

const PAGE_SIZE = 25;

function formatTime(timestamp) {
  return timestamp ? new Date(timestamp).toLocaleString() : "Never";
}

function InventoryTable({ rows, headers, cells, label }) {
  const [page, setPage] = useState(0);
  const pages = Math.ceil(rows.length / PAGE_SIZE);
  const current = Math.min(page, Math.max(0, pages - 1));

  return <section className="card">
    <h2>{label} ({rows.length})</h2>
    {rows.length ? <>
      <div className="design-table">
        <table className="table">
          <thead><tr>{headers.map((title) => <th key={title} scope="col">{title}</th>)}</tr></thead>
          <tbody>{rows.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE).map((row) => (
            <tr key={row.id}>{cells(row).map((cell, index) => <td key={headers[index]}>{cell || "—"}</td>)}</tr>
          ))}</tbody>
        </table>
      </div>
      {pages > 1 && <div className="actions">
        <button onClick={() => setPage(current - 1)} disabled={current === 0}>Previous</button>
        <span aria-live="polite">Page {current + 1} of {pages}</span>
        <button onClick={() => setPage(current + 1)} disabled={current >= pages - 1}>Next</button>
      </div>}
    </> : <p>No rows to display.</p>}
  </section>;
}

export default function AzureInventoryWorkspace({ canRefresh }) {
  const [connection, setConnection] = useState(null);
  const [subscription, setSubscription] = useState("");
  const [inventory, setInventory] = useState(null);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const subscriptions = connection?.configured_subscription_ids
    || (connection?.configured_subscription_id ? [connection.configured_subscription_id] : []);

  useEffect(() => {
    getAzureConnectionStatus().then((status) => {
      setConnection(status);
      setSubscription(status.configured_subscription_id || "");
    }).catch((failure) => {
      if (failure.name !== "AbortError") setError(failure.message);
    }).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!subscription) return undefined;
    let active = true;
    setLoading(true);
    setError("");
    getAzureInventory(subscription).then((data) => {
      if (active) setInventory(data);
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") setError(failure.message);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [subscription]);

  async function refresh() {
    setRefreshing(true);
    setError("");
    try {
      setInventory(await refreshAzureInventory(subscription));
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setRefreshing(false);
    }
  }

  const query = filter.trim().toLowerCase();
  const resources = useMemo(() => (inventory?.resources || []).filter((item) => !query ||
    [item.name, item.type, item.resource_group, item.location].some((value) => value?.toLowerCase().includes(query))), [inventory, query]);
  const groups = useMemo(() => (inventory?.resource_groups || []).filter((item) => !query ||
    [item.name, item.location].some((value) => value?.toLowerCase().includes(query))), [inventory, query]);

  return <section className="workspace-panel">
    <div className="workspace-header"><div>
      <h1>Azure Inventory</h1>
      <p>Browse the resources and resource groups collected from this client's Azure subscriptions.</p>
    </div></div>
    {error && <div className="error" role="alert">{error}</div>}
    {loading && <p role="status">Loading Azure inventory…</p>}
    {!loading && connection && subscriptions.length === 0 && <p>{STATUS_TEXT.not_configured}</p>}
    {subscription && <section className="card account-form">
      <label>Subscription<select value={subscription} disabled={refreshing} onChange={(event) => {
        setInventory(null);
        setFilter("");
        setSubscription(event.target.value);
      }}>
        {subscriptions.map((id) => <option key={id} value={id}>{id}</option>)}
      </select></label>
      {canRefresh && <div><button disabled={loading || refreshing} onClick={refresh}>{refreshing ? "Refreshing…" : "Refresh inventory"}</button></div>}
      {inventory && <>
        <p role="status">{STATUS_TEXT[inventory.status] || inventory.status}</p>
        {inventory.failure_reason && <div className="error" role="alert">
          <p>Failed stage: {inventory.failure_stage || "inventory collection"}. Reason: {inventory.failure_reason}.</p>
          <p>{FAILURE_ACTION[inventory.failure_reason] || STATUS_TEXT[inventory.failure_reason] || "Retry collection and use the support reference if it repeats."}</p>
          {inventory.correlation_id && <p>Support reference: <code>{inventory.correlation_id}</code></p>}
        </div>}
        {inventory.showing_retained_data && <p><strong>Previously collected data is shown below.</strong> It is not evidence that the current Azure state is healthy.</p>}
        <p>Last attempt {formatTime(inventory.last_attempt_at)} · Last successful refresh {formatTime(inventory.last_success_at)}</p>
      </>}
    </section>}
    {inventory && <section className="account-form">
      <label>Filter inventory<input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Name, type, group, or location" /></label>
      <InventoryTable key={`resources-${query}`} rows={resources} label="Resources" headers={["Name", "Type", "Resource group", "Location"]}
        cells={(item) => [item.name, item.type, item.resource_group, item.location]} />
      <InventoryTable key={`groups-${query}`} rows={groups} label="Resource groups" headers={["Name", "Location"]}
        cells={(item) => [item.name, item.location]} />
    </section>}
  </section>;
}
