import { useState } from "react";
import { getGitHubPipeline } from "../services/api";
import { displayLabel, snapshotTime } from "./AzureSnapshotWorkspace";

export default function GitHubPipelineWorkspace() {
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
      <p>Review recent GitHub Actions outcomes for a public repository.</p>
    </div></header>
    <section className="card account-form">
      <h2>GitHub Actions evidence</h2>
      <form className="account-form" onSubmit={load}>
        <fieldset disabled={busy}>
          <label>Repository owner<input name="owner" maxLength={39} required /></label>
          <label>Repository name<input name="repository" maxLength={100} required /></label>
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
              <th scope="col">Event</th><th scope="col">Outcome</th><th scope="col">Created</th>
            </tr></thead>
            <tbody>{evidence.runs.map((run) => <tr key={run.id}>
              <td><a href={`https://github.com/${evidence.repository}/actions/runs/${run.id}`}
                target="_blank" rel="noreferrer">{run.name || `Run ${run.id}`}</a></td>
              <td>{run.head_branch || "Unknown"} <code title={run.head_sha}>{run.head_sha.slice(0, 12)}</code></td>
              <td>{displayLabel(run.event)}</td>
              <td>{displayLabel(run.conclusion || run.status)}</td>
              <td>{snapshotTime(run.created_at)}</td>
            </tr>)}</tbody>
          </table></div>
        </> : <p>No workflow runs were returned for this repository.</p>}
      </>}
    </section>
  </section>;
}
