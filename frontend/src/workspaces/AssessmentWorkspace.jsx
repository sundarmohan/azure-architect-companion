import { useEffect, useState } from "react";
import {
  createAssessment,
  getAssessment,
  importAssessmentFindings,
  listAssessments,
  updateAssessmentFinding,
} from "../services/api";
import { displayLabel } from "./AzureSnapshotWorkspace";

const SEVERITIES = ["critical", "high", "medium", "low", "informational"];
const STATUSES = ["open", "confirmed", "in_remediation", "ready_for_retest", "closed"];
const NEXT_STATUSES = {
  open: ["confirmed"],
  confirmed: ["in_remediation", "open"],
  in_remediation: ["ready_for_retest", "open"],
  ready_for_retest: ["closed", "in_remediation", "open"],
  closed: ["open"],
};
const IMPORT_FIELDS = ["external_id", "title", "severity", "source", "evidence"];
const OPTIONAL_IMPORT_FIELDS = ["tool_version", "methodology", "observed_at"];
const PAGE_SIZE = 20;
const IMPORT_LIMITS = { external_id: 160, title: 240, source: 100, evidence: 2000, tool_version: 100, methodology: 400 };

function formatTime(value) {
  return new Date(value).toLocaleString();
}

function parseFindings(raw) {
  let findings;
  try {
    findings = JSON.parse(raw);
  } catch {
    throw new Error("Enter a valid JSON array of findings.");
  }
  if (!Array.isArray(findings) || !findings.length) throw new Error("Enter a JSON array containing at least one finding.");
  if (findings.length > 100) throw new Error("Import up to 100 findings at a time.");
  return findings.map((finding, index) => {
    if (!finding || IMPORT_FIELDS.some((field) => typeof finding[field] !== "string" || !finding[field].trim())) {
      throw new Error(`Finding ${index + 1} requires text for external_id, title, severity, source, and evidence.`);
    }
    if (!SEVERITIES.includes(finding.severity)) throw new Error(`Finding ${index + 1} has an invalid severity.`);
    const row = Object.fromEntries(IMPORT_FIELDS.map((field) => [field, finding[field].trim()]));
    for (const field of OPTIONAL_IMPORT_FIELDS) {
      if (finding[field] == null) continue;
      if (typeof finding[field] !== "string") throw new Error(`Finding ${index + 1} requires text for ${field}.`);
      const value = finding[field].trim();
      if (value) row[field] = value;
    }
    for (const [field, limit] of Object.entries(IMPORT_LIMITS)) {
      if (row[field]?.length > limit) throw new Error(`Finding ${index + 1} exceeds the ${field} limit of ${limit} characters.`);
    }
    if (row.observed_at && (!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(row.observed_at) || !Number.isFinite(Date.parse(row.observed_at)))) {
      throw new Error(`Finding ${index + 1} requires an observed_at timestamp with a timezone.`);
    }
    return row;
  });
}

function exportReport(assessment) {
  const blob = new Blob([JSON.stringify(assessment, null, 2)], { type: "application/json" });
  const resource = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = resource;
  link.download = `assessment-${assessment.id}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(resource), 0);
}

function CreateAssessment({ onCreate }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const start = new Date(fields.get("window_start"));
    const end = new Date(fields.get("window_end"));
    const name = fields.get("name").trim();
    const scope = fields.get("scope").trim();
    const authorization = fields.get("authorization").trim();
    const environment = fields.get("environment").trim();
    setError("");
    if (!name || !scope || !authorization) {
      setError("Enter a name, scope, and authorization reference.");
      return;
    }
    if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start) {
      setError("Enter an assessment window with an end time after its start.");
      return;
    }
    setBusy(true);
    try {
      const assessment = await createAssessment({
        name, scope, authorization,
        ...(environment ? { environment } : {}),
        window_start: start.toISOString(),
        window_end: end.toISOString(),
      });
      onCreate(assessment);
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  return <form className="card account-form" onSubmit={submit}>
    <h2>Record an assessment</h2>
    {error && <p className="error" role="alert">{error}</p>}
    <fieldset disabled={busy}>
      <label>Assessment name<input name="name" maxLength={180} required /></label>
      <label>Environment<input name="environment" maxLength={80} /></label>
      <label>Scope and exclusions<textarea name="scope" rows={3} maxLength={4000} required /></label>
      <label>Authorization reference<textarea name="authorization" rows={3} maxLength={2000} required /></label>
      <p>Enter the approved window in your local time.</p>
      <div className="grid">
        <label>Window start<input name="window_start" type="datetime-local" required /></label>
        <label>Window end<input name="window_end" type="datetime-local" required /></label>
      </div>
      <div><button type="submit">{busy ? "Saving…" : "Create assessment"}</button></div>
    </fieldset>
  </form>;
}

function ImportFindings({ id, onImport }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    const form = event.currentTarget;
    setMessage("");
    setError("");
    setBusy(true);
    try {
      const findings = parseFindings(new FormData(form).get("findings"));
      const result = await importAssessmentFindings(id, { findings });
      form.reset();
      setMessage(`Imported ${result.inserted} · Duplicates skipped ${result.duplicates}`);
      await onImport();
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  return <form className="card account-form" onSubmit={submit}>
    <h2>Import findings</h2>
    <p>Paste a JSON array of reviewed findings. Each entry needs <code>external_id</code>, <code>title</code>, <code>severity</code>, <code>source</code>, and <code>evidence</code> as text.</p>
    <p>Severity values are {SEVERITIES.join(", ")}. Use sanitized evidence and omit secrets and patient data.</p>
    <p>Optional fields are <code>tool_version</code>, <code>methodology</code>, and <code>observed_at</code> (ISO timestamp with timezone).</p>
    <fieldset disabled={busy}>
      <label>Findings JSON<textarea name="findings" rows={6} required spellCheck={false} /></label>
      <div><button type="submit">{busy ? "Importing…" : "Import findings"}</button></div>
    </fieldset>
    {error && <p className="error" role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
  </form>;
}

function AssessmentFinding({ assessmentId, finding, canEdit, onSave }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const availableStatuses = [finding.status, ...(NEXT_STATUSES[finding.status] || [])];

  async function save(event) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    setError("");
    setMessage("");
    const status = fields.get("status");
    const retestNote = fields.get("retest_note").trim();
    if (status === "closed" && !retestNote) {
      setError("Enter a retest note before closing the finding.");
      return;
    }
    setBusy(true);
    try {
      const next = await updateAssessmentFinding(assessmentId, finding.id, {
        status,
        owner: fields.get("owner").trim() || null,
        due_date: fields.get("due_date") || null,
        retest_note: retestNote || null,
      });
      setMessage("Finding updated.");
      await onSave(next);
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  return <li>
    <strong>{finding.title}</strong>
    <span>{displayLabel(finding.severity)} · {displayLabel(finding.status)} · {finding.source} · {finding.external_id}</span>
    <dl className="design-meta">
      <div><dt>Owner</dt><dd>{finding.owner || "Unassigned"}</dd></div>
      <div><dt>Due date</dt><dd>{finding.due_date || "None"}</dd></div>
    </dl>
    <details><summary>Evidence and retest notes</summary>
      <p>{finding.evidence}</p>
      {finding.tool_version && <p>Tool version {finding.tool_version}</p>}
      {finding.methodology && <p>Methodology {finding.methodology}</p>}
      {finding.observed_at && <p>Observed {formatTime(finding.observed_at)}</p>}
      {finding.retest_note && <p>Retest note {finding.retest_note}</p>}
    </details>
    {finding.history?.length > 0 && <details>
      <summary>Finding history</summary>
      <ol>{finding.history.map((event, index) => <li key={`${event.created_at}-${index}`}>
        <strong>{displayLabel(event.status)}</strong><span>{formatTime(event.created_at)}</span>
        {event.note && <p>{event.note}</p>}
      </li>)}</ol>
    </details>}
    {canEdit && <details>
      <summary>Update finding</summary>
      <form className="account-form" key={JSON.stringify([finding.status, finding.owner, finding.due_date, finding.retest_note])} onSubmit={save}>
        <fieldset disabled={busy}>
          <label>Finding status<select name="status" defaultValue={finding.status}>
            {availableStatuses.map((status) => <option key={status} value={status}>{displayLabel(status)}</option>)}
          </select></label>
          <label>Finding owner<input name="owner" maxLength={120} defaultValue={finding.owner || ""} /></label>
          <label>Finding due date<input name="due_date" type="date" defaultValue={finding.due_date || ""} /></label>
          <label>Retest note<textarea name="retest_note" rows={3} maxLength={2000} defaultValue={finding.retest_note || ""} /></label>
          <div><button type="submit">{busy ? "Saving…" : "Save finding"}</button></div>
        </fieldset>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
    </details>}
  </li>;
}

function AssessmentDetail({ assessment, canEdit, onBack, onImport, onSave }) {
  const [severity, setSeverity] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(0);
  const findings = assessment.findings;
  const filtered = findings.filter((finding) => (!severity || finding.severity === severity) && (!status || finding.status === status))
    .sort((first, second) => SEVERITIES.indexOf(first.severity) - SEVERITIES.indexOf(second.severity));
  const pages = Math.ceil(filtered.length / PAGE_SIZE);
  const currentPage = Math.min(Math.max(0, pages - 1), page);

  return <>
    <section className="card account-form">
      <div className="actions">
        <button type="button" className="dismiss" onClick={onBack}>All assessments</button>
        <button type="button" onClick={() => exportReport(assessment)}>Export assessment JSON</button>
      </div>
      <h2>{assessment.name}</h2>
      <dl className="design-meta">
        {assessment.environment && <div><dt>Environment</dt><dd>{assessment.environment}</dd></div>}
        <div><dt>Window start</dt><dd>{formatTime(assessment.window_start)}</dd></div>
        <div><dt>Window end</dt><dd>{formatTime(assessment.window_end)}</dd></div>
      </dl>
      <h3>Scope and exclusions</h3>
      <p>{assessment.scope}</p>
      <h3>Authorization reference</h3>
      <p>{assessment.authorization}</p>
    </section>
    {canEdit && <ImportFindings id={assessment.id} onImport={onImport} />}
    <section className="card account-form">
      <h2>Findings ({findings.length})</h2>
      {findings.length > 0 && <div className="grid">
        <label>Filter by severity<select value={severity} onChange={(event) => { setSeverity(event.target.value); setPage(0); }}>
          <option value="">All severities</option>
          {SEVERITIES.map((value) => <option key={value} value={value}>{displayLabel(value)}</option>)}
        </select></label>
        <label>Filter by status<select value={status} onChange={(event) => { setStatus(event.target.value); setPage(0); }}>
          <option value="">All statuses</option>
          {STATUSES.map((value) => <option key={value} value={value}>{displayLabel(value)}</option>)}
        </select></label>
      </div>}
      {filtered.length > 0 ? <ul className="design-list">
        {filtered.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE).map((finding) => (
          <AssessmentFinding key={finding.id} assessmentId={assessment.id} finding={finding} canEdit={canEdit} onSave={onSave} />
        ))}
      </ul> : <p>{findings.length ? "No findings match these filters." : "No findings have been imported."}</p>}
      {pages > 1 && <div className="actions">
        <button disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous</button>
        <span aria-live="polite">Page {currentPage + 1} of {pages}</span>
        <button disabled={currentPage + 1 === pages} onClick={() => setPage(currentPage + 1)}>Next</button>
      </div>}
    </section>
  </>;
}

export default function AssessmentWorkspace({ canEdit }) {
  const [assessments, setAssessments] = useState(null);
  const [selected, setSelected] = useState(null);
  const [creating, setCreating] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    listAssessments().then((data) => {
      if (active) setAssessments(data);
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") setError(failure.message);
    });
    return () => { active = false; };
  }, []);

  async function openAssessment(id) {
    setLoadingDetail(true);
    setError("");
    try {
      setSelected(await getAssessment(id));
      setCreating(false);
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setLoadingDetail(false);
    }
  }

  async function reloadDetails(id) {
    const refreshed = await getAssessment(id);
    setSelected((current) => current?.id === id ? refreshed : current);
  }

  return <section className="workspace-panel azure-observability">
    <div className="workspace-header"><div>
      <h1>Assessments &amp; Vulnerabilities</h1>
      <p>Record assessment scope and authorization, import reviewed findings, and track remediation and retesting.</p>
    </div></div>
    {error && <p className="error" role="alert">{error}</p>}
    {selected ? <AssessmentDetail key={selected.id} assessment={selected} canEdit={canEdit}
      onBack={() => setSelected(null)}
      onImport={() => reloadDetails(selected.id)}
      onSave={async (next) => {
        setSelected((current) => current?.id === selected.id ? ({
          ...current,
          findings: current.findings.map((finding) => finding.id === next.id
            ? { ...next, history: next.history?.length ? next.history : finding.history }
            : finding),
        }) : current);
        await reloadDetails(selected.id);
      }} /> : <>
      {canEdit && <div className="actions"><button type="button" disabled={loadingDetail || !assessments}
        aria-expanded={creating} onClick={() => setCreating(!creating)}>
        {creating ? "Cancel new assessment" : "New assessment"}
      </button></div>}
      {creating && <CreateAssessment onCreate={(record) => {
        setAssessments((current) => [record, ...(current || [])]);
        setSelected(record);
        setCreating(false);
      }} />}
      <section className="card account-form">
        <h2>Saved assessments</h2>
        {loadingDetail && <p role="status">Loading assessment…</p>}
        {!assessments && !error && <p role="status">Loading assessments…</p>}
        {assessments && (assessments.length ? <ul className="design-list">{assessments.map((record) => (
          <li key={record.id}>
            <strong>{record.name}</strong>
            <span>{formatTime(record.window_start)} – {formatTime(record.window_end)}</span>
            <div><button type="button" disabled={loadingDetail} onClick={() => openAssessment(record.id)}>Open {record.name}</button></div>
          </li>
        ))}</ul> : <p>No assessments recorded.</p>)}
      </section>
    </>}
  </section>;
}
