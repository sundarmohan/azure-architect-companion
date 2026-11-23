import { useEffect, useState } from "react";
import { getAzureHealthIncidents, updateAzureHealthIncident } from "../services/api";
import AzureIncidentActions from "./AzureIncidentActions";
import AzureIncidentSecurityEvidence from "./AzureIncidentSecurityEvidence";
import { displayLabel, snapshotTime } from "./AzureSnapshotWorkspace";

function IncidentRecord({ incident, subscription, canEdit, onUpdate, initiallyOpen }) {
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const [showActions, setShowActions] = useState(false);
  const [showSecurityEvidence, setShowSecurityEvidence] = useState(false);

  async function save(event) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    setBusy(true);
    setFeedback("");
    setError("");
    try {
      const updated = await updateAzureHealthIncident(subscription, incident.id, {
        status: values.get("status"),
        owner: values.get("owner").trim() || null,
        rca_note: values.get("rca_note").trim() || null,
        updated_at: incident.updated_at,
      });
      onUpdate(updated);
      setFeedback("Incident updated.");
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  return <li>
    <details open={initiallyOpen}>
      <summary>{incident.resource_id} · {displayLabel(incident.status)}</summary>
      <dl className="design-meta">
        <div><dt>Reported health</dt><dd>{displayLabel(incident.health)}</dd></div>
        <div><dt>Evidence collected</dt><dd>{snapshotTime(incident.collected_at)}</dd></div>
        <div><dt>Evidence acknowledged</dt><dd>{snapshotTime(incident.acknowledged_at)}</dd></div>
        <div><dt>Evidence reference</dt><dd><code>{incident.evidence_id}</code></dd></div>
        <div><dt>Owner</dt><dd>{incident.owner || "Unassigned"}</dd></div>
        {incident.rca_note && <div><dt>Investigation and RCA note</dt><dd>{incident.rca_note}</dd></div>}
      </dl>
      {canEdit && <form className="account-form" key={incident.updated_at} onSubmit={save}>
        <fieldset disabled={busy}>
          <label>Incident status<select name="status" defaultValue={incident.status}>
            <option value="open">Open</option>
            <option value="investigating">Investigating</option>
            <option value="resolved">Resolved</option>
          </select></label>
          <label>Incident owner<input name="owner" maxLength={120} defaultValue={incident.owner || ""} /></label>
          <label>Investigation and RCA note<textarea name="rca_note" maxLength={4000} rows={3}
            defaultValue={incident.rca_note || ""} /></label>
          <p>Resolving an incident requires a note.</p>
          <div><button type="submit">{busy ? "Saving..." : "Save incident"}</button></div>
        </fieldset>
      </form>}
      {error && <p className="error" role="alert">{error}</p>}
      {feedback && <p role="status">{feedback}</p>}
      <div><button type="button" aria-expanded={showActions} onClick={() => setShowActions((visible) => !visible)}>
        {showActions ? "Hide incident actions" : "Show incident actions"}
      </button></div>
      {showActions && <AzureIncidentActions subscription={subscription} incidentId={incident.id} canEdit={canEdit} />}
      <div><button type="button" aria-expanded={showSecurityEvidence}
        onClick={() => setShowSecurityEvidence((visible) => !visible)}>
        {showSecurityEvidence ? "Hide Security evidence" : "Show Security evidence"}
      </button></div>
      {showSecurityEvidence && <AzureIncidentSecurityEvidence subscription={subscription}
        incidentId={incident.id} canEdit={canEdit} />}
    </details>
  </li>;
}

export default function AzureHealthIncidents({ subscription, canEdit, initialIncident }) {
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(initialIncident);
  const [readCount, setReadCount] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    getAzureHealthIncidents(subscription, page).then((data) => {
      if (active) setResult(data);
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") setError(failure.message);
    });
    return () => { active = false; };
  }, [subscription, page, readCount]);

  function showPage(next) {
    setError("");
    setResult(null);
    if (next === page) setReadCount((value) => value + 1);
    else setPage(next);
  }

  function updateRecord(updated) {
    setSelected((current) => current?.id === updated.id ? updated : current);
    setResult((current) => current && ({
      ...current,
      incidents: current.incidents.map((item) => item.id === updated.id ? updated : item),
    }));
  }

  const additional = result?.incidents.filter((incident) => incident.id !== selected?.id) || [];
  return <>
    {selected && <ul className="design-list">
      <IncidentRecord incident={selected} subscription={subscription} canEdit={canEdit}
        onUpdate={updateRecord} initiallyOpen />
    </ul>}
    <div><button type="button" className="dismiss" onClick={() => showPage(page)}>Reload health incidents</button></div>
    {error && <p className="error" role="alert">{error}</p>}
    {!result && !error && <p role="status">Loading health incidents...</p>}
    {result && (additional.length ? <ul className="design-list">
      {additional.map((incident) => <IncidentRecord key={incident.id} incident={incident} subscription={subscription}
        canEdit={canEdit} onUpdate={updateRecord} />)}
    </ul> : <p>{selected ? "No other health incidents on this page." : "No health incidents on this page."}</p>)}
    {(page > 1 || result?.has_next) && <div className="actions">
      <button type="button" disabled={page === 1} onClick={() => showPage(page - 1)}>Previous incidents</button>
      <span>Page {page}</span>
      <button type="button" disabled={!result?.has_next} onClick={() => showPage(page + 1)}>Next incidents</button>
    </div>}
  </>;
}
