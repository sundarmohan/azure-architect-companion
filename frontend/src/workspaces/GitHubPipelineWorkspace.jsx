import { useState } from "react";
import { getGitHubDependencyAlerts, getGitHubPipeline } from "../services/api";
import { displayLabel, snapshotTime } from "./AzureSnapshotWorkspace";
import GitHubConnectionSettings from "./GitHubConnectionSettings";
import RepositoryFindings from "./RepositoryFindings";

function DependencyEvidence() {
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function load() {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setResult(await getGitHubDependencyAlerts());
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setBusy(false);
    }
  }
  return <section className="card account-form">
    <h2>Dependabot evidence</h2>
    <p>Read the first 20 alerts for the configured repository. The connection needs read access to Dependabot alerts.</p>
    <div><button type="button" disabled={busy} onClick={load}>{busy ? "Loading alerts..." : "Load dependency alerts"}</button></div>
    {error && <p className="error" role="alert">{error}</p>}
    {result && <>
      <p>{result.repository} | Collected {snapshotTime(result.collected_at)}</p>
      {result.alerts.length ? <ul className="design-list">{result.alerts.map((alert) => <li key={alert.number}>
        <strong>{alert.package || "Dependency alert"}</strong>
        <span>{displayLabel(alert.severity)} | {displayLabel(alert.state)}{alert.manifest && ` | ${alert.manifest}`}</span>
        {alert.patched_version && <span>Patched version {alert.patched_version}</span>}
        <a href={`https://github.com/${result.repository}/security/dependabot/${alert.number}`} target="_blank" rel="noreferrer">Review GitHub alert {alert.number}</a>
      </li>)}</ul> : <p>GitHub returned no dependency alerts.</p>}
    </>}
  </section>;
}

export default function GitHubPipelineWorkspace({ canEdit = false, canManageConnection = false }) {
  const [showConnection, setShowConnection] = useState(false);
  const [configured, setConfigured] = useState(null);
  const [connectionRevision, setConnectionRevision] = useState(0);
  const [showFindings, setShowFindings] = useState(false);
  const [busy, setBusy] = useState(false);
  const [evidence, setEvidence] = useState(null);
  const [error, setError] = useState("");

  async function load(event) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setEvidence(null);
    try {
      setEvidence(await getGitHubPipeline(fields.get("owner").trim(), fields.get("repository").trim()));
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  return <section className="workspace-panel azure-observability">
    <header className="workspace-header"><div><h1>DevSecOps</h1>
      <p>Review recent GitHub Actions outcomes for a public or configured repository.</p>
    </div></header>
    <section className="card account-form">
      <h2>GitHub Actions evidence</h2>
      <form className="account-form" onSubmit={load} key={configured && `${configured.owner}/${configured.repository}`}>
        <fieldset disabled={busy}>
          <label>Repository owner<input name="owner" defaultValue={configured?.owner} maxLength={39} required /></label>
          <label>Repository name<input name="repository" defaultValue={configured?.repository} maxLength={100} required /></label>
          <button type="submit">Load workflow runs</button>
        </fieldset>
      </form>
      {busy && <p role="status">Loading workflow runs...</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {evidence && <>
        <p>{evidence.repository} | Collected {snapshotTime(evidence.collected_at)}</p>
        {evidence.runs.length ? <>
          <p>Showing {evidence.runs.length} of {evidence.total_count} reported runs.</p>
          <div className="design-table"><table className="table" aria-label="Recent GitHub Actions runs">
            <thead><tr>
              <th scope="col">Workflow</th><th scope="col">Branch and commit</th>
              <th scope="col">Event</th><th scope="col">Outcome</th><th scope="col">Imported findings</th><th scope="col">Created</th>
            </tr></thead>
            <tbody>{evidence.runs.map((run) => <tr key={run.id}>
              <td><a href={`https://github.com/${evidence.repository}/actions/runs/${run.id}`}
                target="_blank" rel="noreferrer">{run.name || `Run ${run.id}`}</a></td>
              <td>{run.head_branch || "Unknown"} <code title={run.head_sha}>{run.head_sha.slice(0, 12)}</code></td>
              <td>{displayLabel(run.event)}</td>
              <td>{displayLabel(run.conclusion || run.status)}</td>
              <td>{Object.entries(run.finding_counts || {}).map(([severity, count]) =>
                `${count} ${displayLabel(severity)}`).join(", ") || "No matching imported evidence"}</td>
              <td>{snapshotTime(run.created_at)}</td>
            </tr>)}</tbody>
          </table></div>
        </> : <p>No workflow runs were returned for this repository.</p>}
      </>}
    </section>
    <DependencyEvidence key={connectionRevision} />
    <div className="actions"><button type="button" aria-expanded={showFindings} onClick={() => setShowFindings((open) => !open)}>
      {showFindings ? "Hide repository findings" : "Review repository findings"}
    </button></div>
    {showFindings && <RepositoryFindings canEdit={canEdit} />}
    {canManageConnection && <div><button type="button" aria-expanded={showConnection} onClick={() => setShowConnection((open) => !open)}>
      {showConnection ? "Hide GitHub connection" : "Manage GitHub connection"}
    </button></div>}
    {showConnection && canManageConnection && <GitHubConnectionSettings onSaved={(value) => {
      setConfigured(value);
      setEvidence(null);
      setConnectionRevision((previous) => previous + 1);
    }} />}
  </section>;
}
