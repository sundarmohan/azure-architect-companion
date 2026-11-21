import { useEffect, useState } from "react";
import {
  compareDesignRevisions,
  estimateArchitectureCost,
  getAnsibleExport,
  getDesignExport,
  getDesignRevision,
  getDesignValidation,
  listDesignHistory,
  listDesignRevisions,
  restoreDesignRevision,
  saveDesignRevision,
  transitionArchitecture,
} from "../services/api";

const DESIGN_STATUS = {
  draft: "Draft",
  in_review: "In review",
  approved: "Approved",
  archived: "Archived",
};

const STATUS_ACTIONS = {
  draft: [["in_review", "Submit for review"], ["archived", "Archive"]],
  in_review: [["draft", "Return to draft"], ["approved", "Approve", true], ["archived", "Archive"]],
  approved: [["draft", "Reopen as draft", true], ["archived", "Archive"]],
  archived: [["draft", "Reopen as draft", true]],
};

const EXPORTS = [
  ["definition", "Architecture JSON", "architecture.json"],
  ["diagram", "Diagram SVG", "architecture.svg"],
  ["terraform", "Terraform", "main.tf.json"],
];

export function designStatus(status) {
  return DESIGN_STATUS[status] || status || "Unknown";
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "—";
}

function formatMoney(amount, currency) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(amount) + " " + currency;
}

function downloadArtifact(blob, fileName) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function AnsibleForm({ onExport, busy }) {
  const [serviceIds, setServiceIds] = useState([]);
  const [nextId, setNextId] = useState(1);

  function submit(event) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const packages = fields.get("packages").split(/[\n,]+/).map((name) => name.trim()).filter(Boolean);
    const services = serviceIds.map((id) => ({
      name: fields.get(`name-${id}`).trim(),
      enabled: fields.has(`enabled-${id}`),
      state: fields.get(`state-${id}`),
    }));
    void onExport({ packages, services });
  }

  return <form className="account-form" onSubmit={submit}>
    <h3>Ansible playbook</h3>
    <p>Provide the packages and services to include for the target hosts.</p>
    <fieldset disabled={busy}>
      <label>Packages<textarea name="packages" rows={3} placeholder="One package per line" /></label>
      {serviceIds.map((id, index) => <div key={id} className="design-service">
        <label>Service {index + 1}<input name={`name-${id}`} required /></label>
        <label>State<select name={`state-${id}`} defaultValue="started">
          <option value="started">Started</option>
          <option value="stopped">Stopped</option>
        </select></label>
        <label className="design-checkbox"><input type="checkbox" name={`enabled-${id}`} defaultChecked /> Enabled on boot</label>
        <button type="button" className="dismiss" onClick={() => setServiceIds((current) => current.filter((item) => item !== id))}>Remove service</button>
      </div>)}
      <div className="actions">
        <button type="button" className="dismiss" onClick={() => {
          setServiceIds((current) => [...current, nextId]);
          setNextId(nextId + 1);
        }}>Add service</button>
        <button type="submit">Download Ansible</button>
      </div>
    </fieldset>
  </form>;
}

export default function DesignDetails({ design, canEdit, canApprove, onBack, onOpenDesigner, onEdit, onDuplicate, onDelete, onUpdate }) {
  const [history, setHistory] = useState(null);
  const [revisions, setRevisions] = useState(null);
  const [revision, setRevision] = useState(null);
  const [compareAgainst, setCompareAgainst] = useState("");
  const [changes, setChanges] = useState(null);
  const [validation, setValidation] = useState(null);
  const [estimate, setEstimate] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const draft = design.status === "draft";
  const actions = (STATUS_ACTIONS[design.status] || []).filter(([, , adminOnly]) => canEdit && (!adminOnly || canApprove));

  useEffect(() => {
    let active = true;
    listDesignHistory(design.id).then((data) => {
      if (active) setHistory(data);
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") {
        setHistory([]);
        setError(failure.message);
      }
    });
    listDesignRevisions(design.id).then((data) => {
      if (active) setRevisions(data);
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") {
        setRevisions([]);
        setError(failure.message);
      }
    });
    return () => { active = false; };
  }, [design.id]);

  async function run(action, message) {
    setBusy(true);
    setError("");
    setFeedback("");
    try {
      await action();
      if (message) setFeedback(message);
      return true;
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function refreshHistory() {
    const [statusHistory, designRevisions] = await Promise.all([listDesignHistory(design.id), listDesignRevisions(design.id)]);
    setHistory(statusHistory);
    setRevisions(designRevisions);
  }

  function applyStatus(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    const status = event.nativeEvent.submitter?.value;
    if (!status) return;
    void run(async () => {
      onUpdate(await transitionArchitecture(design.id, { status, note: fields.get("note").trim() || null }));
      form.reset();
      await refreshHistory();
    }, `Design moved to ${designStatus(status).toLowerCase()}.`);
  }

  function submitRevision(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const description = new FormData(form).get("description").trim();
    if (!description) return;
    void run(async () => {
      await saveDesignRevision(design.id, { description });
      form.reset();
      setRevisions(await listDesignRevisions(design.id));
    }, "Revision saved.");
  }

  function restore(event) {
    event.preventDefault();
    const description = new FormData(event.currentTarget).get("description").trim();
    if (!description || !window.confirm(`Restore revision ${revision.number} as the current draft?`)) return;
    void run(async () => {
      onUpdate(await restoreDesignRevision(design.id, revision.id, { description }));
      setRevision(null);
      setChanges(null);
      setValidation(null);
      setEstimate(null);
      await refreshHistory();
    }, `Revision ${revision.number} restored.`);
  }

  return <section className="design-details">
    <div className="card">
      <div className="actions">
        <button className="dismiss" onClick={onBack} disabled={busy}>All designs</button>
        <button onClick={onOpenDesigner} disabled={busy}>Open designer</button>
        {canEdit && draft && <button className="dismiss" onClick={onEdit} disabled={busy}>Edit details</button>}
        {canEdit && <button className="dismiss" onClick={onDuplicate} disabled={busy}>Duplicate</button>}
        {canApprove && design.status === "archived" && <button className="danger" onClick={onDelete} disabled={busy}>Delete design</button>}
      </div>
      <h2>{design.name}</h2>
      <dl className="design-meta">
        <div><dt>Status</dt><dd>{designStatus(design.status)}</dd></div>
        <div><dt>Project</dt><dd>{design.project || "Unassigned"}</dd></div>
        <div><dt>Environment</dt><dd>{design.environment}</dd></div>
        <div><dt>Default region</dt><dd>{design.default_region || "Unspecified"}</dd></div>
      </dl>
      {design.description && <p>{design.description}</p>}
      {error && <div className="error" role="alert">{error}</div>}
      {feedback && <p role="status">{feedback}</p>}
    </div>

    <div className="grid account-grid">
      <section className="card account-form">
        <h2>Review and approval</h2>
        {actions.length > 0 && <form onSubmit={applyStatus}>
          <fieldset disabled={busy}>
            <label>Review note<textarea name="note" rows={2} maxLength={1000} /></label>
            <div className="actions">{actions.map(([target, title]) => (
              <button key={target} type="submit" value={target}>{title}</button>
            ))}</div>
          </fieldset>
        </form>}
        {history === null ? <p>Loading review history…</p> : history.length ? <ul className="design-list">{history.map((event) => (
          <li key={event.id}>
            <strong>{event.from_status ? `${designStatus(event.from_status)} → ` : ""}{designStatus(event.to_status)}</strong>
            <span>{event.actor || "Unknown user"} · {formatDate(event.created_at)}</span>
            {event.note && <p>{event.note}</p>}
          </li>
        ))}</ul> : <p>No review history.</p>}
      </section>

      <section className="card account-form">
        <h2>Validation</h2>
        <div><button disabled={busy} onClick={() => run(async () => setValidation(await getDesignValidation(design.id)))}>Run validation</button></div>
        {validation && (validation.findings.length ? <ul className="design-list">{validation.findings.map((finding, index) => (
          <li key={`${finding.code}-${finding.resource_id}-${index}`}>
            <strong>{finding.severity} · {finding.code}</strong>
            <span>{finding.message}</span>
            {finding.resource_id && <small>Resource {finding.resource_id}</small>}
          </li>
        ))}</ul> : <p>No findings were reported.</p>)}
      </section>
    </div>

    <section className="card account-form">
      <h2>Revisions</h2>
      {canEdit && draft && <form onSubmit={submitRevision}>
        <fieldset disabled={busy}>
          <label>Revision description<input name="description" maxLength={1000} required /></label>
          <div><button type="submit">Save revision</button></div>
        </fieldset>
      </form>}
      {revisions === null ? <p>Loading revisions…</p> : revisions.length ? <ul className="design-list">{revisions.map((item) => (
        <li key={item.id}>
          <div><button className="dismiss" disabled={busy} onClick={() => run(async () => {
            setRevision(await getDesignRevision(design.id, item.id));
            setCompareAgainst("");
            setChanges(null);
          })}>Open revision {item.number}</button></div>
          <strong>{item.description}</strong><span>{item.actor || "Unknown user"} · {formatDate(item.created_at)}</span>
        </li>
      ))}</ul> : <p>No saved revisions.</p>}
      {revision && <section className="account-form design-selected">
        <h3>Revision {revision.number}</h3>
        <p>{revision.description}</p>
        <details><summary>View saved architecture data</summary><pre>{JSON.stringify(revision.snapshot, null, 2)}</pre></details>
        {revisions.length > 1 && <>
          <label>Compare to revision<select value={compareAgainst} disabled={busy} onChange={(event) => {
            setCompareAgainst(event.target.value);
            setChanges(null);
          }}>
            <option value="">Select a revision</option>
            {revisions.filter(({ id }) => id !== revision.id).map((item) => <option key={item.id} value={item.id}>Revision {item.number}</option>)}
          </select></label>
          <div><button disabled={!compareAgainst || busy} onClick={() => run(async () => {
            setChanges((await compareDesignRevisions(design.id, revision.id, compareAgainst)).changes);
          })}>Compare revisions</button></div>
        </>}
        {changes && (changes.length ? <ul className="design-list">{changes.map((change, index) => (
          <li key={`${change.section}-${change.id}-${index}`}>
            <strong>{change.kind} · {change.section} {change.id}</strong>
            <details><summary>Before and after</summary><pre>{JSON.stringify({ before: change.before, after: change.after }, null, 2)}</pre></details>
          </li>
        ))}</ul> : <p>No changes between these revisions.</p>)}
        {canEdit && draft && <form onSubmit={restore}>
          <fieldset disabled={busy}>
            <label>Restore description<input name="description" maxLength={1000} required /></label>
            <div><button type="submit">Restore revision</button></div>
          </fieldset>
        </form>}
      </section>}
    </section>

    {canEdit && <section className="card account-form">
      <h2>Planned cost</h2>
      <p>Estimates depend on Azure region, SKU, quantity, and available pricing.</p>
      <div><button disabled={busy} onClick={() => run(async () => setEstimate(await estimateArchitectureCost(design.id)))}>Estimate cost</button></div>
      {estimate && <>
        <p><strong>{formatMoney(estimate.total_monthly_cost, estimate.currency)}</strong> per month · {formatMoney(estimate.total_annual_cost, estimate.currency)} per year</p>
        {!!estimate.items.length && <div className="design-table"><table className="table">
          <thead><tr><th scope="col">Resource</th><th scope="col">Region</th><th scope="col">SKU</th><th scope="col">Quantity</th><th scope="col">Monthly estimate</th><th scope="col">Source</th></tr></thead>
          <tbody>{estimate.items.map((item) => <tr key={item.resource_id}>
            <td>{item.name}</td><td>{item.region}</td><td>{item.sku || "—"}</td><td>{item.quantity}</td>
            <td>{item.error ? "Unavailable" : formatMoney(item.monthly_cost, item.currency)}</td><td>{item.pricing_source.replaceAll("_", " ")}</td>
          </tr>)}</tbody>
        </table></div>}
        {[...estimate.warnings, ...estimate.errors].map((message, index) => <p key={index}>{message}</p>)}
      </>}
    </section>}

    <section className="card account-form">
      <h2>Exports</h2>
      <p>Terraform covers supported Azure resources and lists omissions in the artifact. The Ansible playbook targets Linux hosts you define in your inventory.</p>
      <div className="actions">{EXPORTS.map(([format, title, fileName]) => (
        <button key={format} disabled={busy} onClick={() => run(async () => downloadArtifact(await getDesignExport(design.id, format), fileName))}>Download {title}</button>
      ))}</div>
      {canEdit && <AnsibleForm busy={busy} onExport={(payload) => run(async () => {
        downloadArtifact(await getAnsibleExport(design.id, payload), "playbook.yml");
      })} />}
    </section>
  </section>;
}
