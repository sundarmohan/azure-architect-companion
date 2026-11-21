import { useEffect, useState } from "react";
import { getAzureInventory, queryAzureDiagnostics } from "../services/api";
import { snapshotTime } from "./AzureSnapshotWorkspace";

const SOURCES = [
  ["activity", "Azure Activity Log"],
  ["platform", "Azure platform logs"],
  ["app_service", "App Service logs"],
  ["application", "Application logs"],
  ["guest", "Guest OS logs"],
];
const RANGES = [[1, "Last hour"], [6, "Last 6 hours"], [24, "Last 24 hours"], [72, "Last 72 hours"]];
const STATUS_TEXT = {
  ok: "Azure returned diagnostic aggregates.",
  no_data: "Azure returned no matching data for this resource and time range.",
  authentication_failure: "Azure authentication failed.",
  permission_failure: "The Azure identity lacks permission to query this source.",
  source_unavailable: "This source is unavailable for the selected resource. Check the Azure log configuration.",
  provider_error: "Azure could not complete the query.",
  partial_failure: "Azure returned incomplete query results. Counts may be partial.",
};
const PAGE_SIZE = 25;

function DiagnosticRows({ rows }) {
  const [page, setPage] = useState(0);
  const pageCount = Math.ceil(rows.length / PAGE_SIZE);
  if (!rows.length) return null;
  return <>
    <div className="design-table"><table className="table">
      <thead><tr><th scope="col">Time bucket</th><th scope="col">Category</th><th scope="col">Event count</th></tr></thead>
      <tbody>{rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map((row, index) => (
        <tr key={`${row.timestamp}-${row.category}-${index}`}>
          <td>{snapshotTime(row.timestamp)}</td><td>{row.category}</td><td>{row.count.toLocaleString()}</td>
        </tr>
      ))}</tbody>
    </table></div>
    {pageCount > 1 && <div className="actions">
      <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
      <span aria-live="polite">Page {page + 1} of {pageCount}</span>
      <button type="button" disabled={page + 1 === pageCount} onClick={() => setPage(page + 1)}>Next</button>
    </div>}
  </>;
}

export default function AzureDiagnostics({ subscription }) {
  const [inventory, setInventory] = useState(null);
  const [resourceId, setResourceId] = useState("");
  const [source, setSource] = useState("activity");
  const [hours, setHours] = useState("24");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  useEffect(() => {
    let active = true;
    getAzureInventory(subscription).then((data) => {
      if (active) setInventory(data);
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") setError(failure.message);
    });
    return () => { active = false; };
  }, [subscription]);

  async function submit(event) {
    event.preventDefault();
    if (!resourceId || busy) return;
    setBusy(true);
    setResult(null);
    setError("");
    try {
      setResult(await queryAzureDiagnostics(subscription, { resource_id: resourceId, source, hours: Number(hours) }));
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  const resources = inventory?.resources || [];
  const sourceLabel = SOURCES.find(([id]) => id === result?.source)?.[1];

  return <section className="card account-form">
    <h2>Advanced Diagnostics</h2>
    <p>Query bounded event counts by resource and source. Results contain aggregate counts.</p>
    {error && <div className="error" role="alert">{error}</div>}
    {!inventory && !error && <p role="status">Loading resources from Azure Inventory…</p>}
    {inventory && resources.length === 0 && <p>Refresh Azure Inventory for this subscription to select a resource.</p>}
    {resources.length > 0 && <form onSubmit={submit}>
      <fieldset disabled={busy}>
        <label>Diagnostic resource<select required value={resourceId} onChange={(event) => {
          setResourceId(event.target.value);
          setResult(null);
        }}>
          <option value="">Select a resource</option>
          {resources.map((resource) => <option key={resource.id} value={resource.id}>{resource.name} · {resource.resource_group || resource.type}</option>)}
        </select></label>
        <label>Log source<select value={source} onChange={(event) => {
          setSource(event.target.value);
          setResult(null);
        }}>
          {SOURCES.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </select></label>
        <label>Time range<select value={hours} onChange={(event) => {
          setHours(event.target.value);
          setResult(null);
        }}>
          {RANGES.map(([count, label]) => <option key={count} value={count}>{label}</option>)}
        </select></label>
        <div><button type="submit" disabled={!resourceId || busy}>{busy ? "Querying Azure…" : "Query diagnostics"}</button></div>
      </fieldset>
    </form>}
    {busy && <p role="status">Waiting for Azure to complete the query.</p>}
    {result && <>
      <p role="status">{STATUS_TEXT[result.status] || "Azure returned a query result."}</p>
      <p>{sourceLabel} · {result.hours} hours</p>
      <DiagnosticRows rows={result.rows} />
    </>}
  </section>;
}
