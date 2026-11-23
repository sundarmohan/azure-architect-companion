import { useEffect, useState } from "react";
import { getDevSecOpsFindings, importDevSecOpsFindings } from "../services/api";
import { displayLabel, snapshotTime } from "./AzureSnapshotWorkspace";

const METADATA = new Set(["owner", "repository", "source", "fingerprint", "category", "severity", "commit_sha", "image"]);

export default function RepositoryFindings({ canEdit }) {
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState(null);
  const [importBusy, setImportBusy] = useState(false);
  const [importResult, setImportResult] = useState("");
  const [importError, setImportError] = useState("");

  useEffect(() => {
    let active = true;
    getDevSecOpsFindings(page).then((data) => {
      if (active) setResult({ data, page, revision });
    }).catch((error) => {
      if (active && error.name !== "AbortError") setResult({ error: error.message, page, revision });
    });
    return () => { active = false; };
  }, [page, revision]);

  async function importBatch(event) {
    event.preventDefault();
    const form = event.currentTarget;
    setImportBusy(true);
    setImportResult("");
    setImportError("");
    try {
      let findings;
      try {
        findings = JSON.parse(new FormData(form).get("findings"));
      } catch {
        throw new Error("Provide a JSON array of finding metadata.");
      }
      if (!Array.isArray(findings) || findings.length < 1 || findings.length > 50 || findings.some((item) =>
        !item || Array.isArray(item) || typeof item !== "object" ||
        Object.entries(item).some(([field, value]) => !METADATA.has(field) || (value !== null && typeof value !== "string"))
      )) {
        throw new Error("Provide 1 to 50 findings using only supported metadata fields.");
      }
      const { inserted, duplicates } = await importDevSecOpsFindings({ findings });
      form.reset();
      setImportResult(`Imported ${inserted} · Duplicates ${duplicates}`);
      setPage(1);
      setRevision((value) => value + 1);
    } catch (error) {
      if (error.name !== "AbortError") setImportError(error.message);
    } finally {
      setImportBusy(false);
    }
  }

  const current = result?.page === page && result?.revision === revision ? result : null;
  return <section className="card account-form">
    <h2>Repository security findings</h2>
    {canEdit && <details><summary>Import sanitized finding metadata</summary>
      <p>Use a JSON array. Required fields are owner, repository, source, fingerprint (64 lowercase SHA-256 hex characters), category, and severity.
        Optional fields are commit_sha and image. Categories are dependency, container, iac, secrets, and dockerfile.</p>
      <p>Review metadata before import. Use a fingerprint for the finding identifier and remove secret values, logs, and source snippets.</p>
      <form className="account-form" onSubmit={importBatch}>
        <fieldset disabled={importBusy}>
          <label>Finding metadata JSON<textarea name="findings" maxLength={50000} rows={5} required /></label>
          <button type="submit">Import findings</button>
        </fieldset>
      </form>
      {importError && <p role="alert" className="error">{importError}</p>}
      {importResult && <p role="status">{importResult}</p>}
    </details>}
    {!current && <p role="status">Loading repository findings…</p>}
    {current?.error && <p role="alert" className="error">{current.error}</p>}
    {current?.data && (current.data.findings.length ? <ul className="design-list">
      {current.data.findings.map((finding) => <li key={finding.id}>
        <strong>{finding.owner}/{finding.repository}</strong>
        <span>{displayLabel(finding.category)} · {displayLabel(finding.severity)} · {finding.source}</span>
        {finding.commit_sha && <span>Commit <code>{finding.commit_sha}</code></span>}
        {finding.image && <span>Image <code>{finding.image}</code></span>}
        <p>{finding.recommendation}</p>
        <span>Imported {snapshotTime(finding.created_at)}</span>
      </li>)}
    </ul> : <p>No imported repository findings on this page.</p>)}
    {(page > 1 || current?.data?.has_next) && <div className="actions">
      <button type="button" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous findings</button>
      <span aria-live="polite">Page {page}</span>
      <button type="button" disabled={!current?.data?.has_next} onClick={() => setPage(page + 1)}>Next findings</button>
    </div>}
  </section>;
}
