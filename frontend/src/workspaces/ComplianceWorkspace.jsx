import { useEffect, useState } from "react";
import { getAzureSecurity, getComplianceReviews, saveComplianceReview } from "../services/api";
import AzureSnapshotWorkspace, { displayLabel, snapshotTime } from "./AzureSnapshotWorkspace";

const THEMES = {
  transport: { name: "Protected transport", codes: ["storage_http_allowed", "storage_legacy_tls"] },
  storage: { name: "Storage access and encryption", codes: ["storage_public_blob_allowed", "sql_tde_disabled"] },
  network: { name: "Network access restrictions", codes: ["vault_public_network", "sql_public_network", "nsg_external_inbound"] },
  recovery: { name: "Key recovery safeguards", codes: ["vault_purge_unprotected"] },
};

function ReviewRecord({ topic, subscription, snapshotAttempt, review, canEdit, onSaved }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  async function save(event) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const optional = (name) => fields.get(name)?.trim() || null;
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      onSaved(await saveComplianceReview(subscription, topic, {
        state: fields.get("state"),
        note: fields.get("note").trim(),
        action: optional("action"),
        owner: optional("owner"),
        due_date: optional("due_date"),
        action_status: optional("action_status"),
        snapshot_attempt_at: snapshotAttempt || null,
      }));
      setSaved(true);
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  return <details>
    <summary>Review record · {review ? displayLabel(review.state) : "Unrecorded"}</summary>
    {review && <>
      <p>{review.note}</p>
      <p>Updated {snapshotTime(review.updated_at)} · Azure evidence {review.evidence_at ? snapshotTime(review.evidence_at) : "Unavailable at review"}</p>
      {review.action && <>
        <p>{review.action} · {displayLabel(review.action_status)}</p>
        <p>Owner {review.owner || "Unassigned"} · Due {review.due_date || "Unscheduled"}</p>
      </>}
    </>}
    {canEdit && <form className="account-form" key={review?.updated_at} onSubmit={save}>
      <fieldset disabled={busy}>
        <label>Review state<select name="state" defaultValue={review?.state || "in_review"}>
          <option value="in_review">In review</option>
          <option value="action_required">Action required</option>
          <option value="reviewed">Reviewed</option>
        </select></label>
        <label>Review notes<textarea name="note" defaultValue={review?.note || ""} maxLength={2000} required /></label>
        <label>Corrective action<textarea name="action" defaultValue={review?.action || ""} maxLength={1200} /></label>
        <label>Action owner<input name="owner" defaultValue={review?.owner || ""} maxLength={120} /></label>
        <label>Action due date<input name="due_date" type="date" defaultValue={review?.due_date || ""} /></label>
        <label>Action status<select name="action_status" defaultValue={review?.action_status || ""}>
          <option value="">No corrective action</option>
          <option value="planned">Planned</option>
          <option value="in_progress">In progress</option>
          <option value="completed">Completed</option>
        </select></label>
        <button type="submit">Save review</button>
      </fieldset>
    </form>}
    {error && <p className="error" role="alert">{error}</p>}
    {saved && <p role="status">Review saved.</p>}
  </details>;
}

function EvidenceReview({ snapshot, subscription, canEdit }) {
  const [reviews, setReviews] = useState(null);
  const [reviewError, setReviewError] = useState("");
  useEffect(() => {
    let active = true;
    getComplianceReviews(subscription).then((rows) => {
      if (active) setReviews(Object.fromEntries(rows.map((row) => [row.topic, row])));
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") setReviewError(failure.message);
    });
    return () => { active = false; };
  }, [subscription]);

  function record(topic) {
    return reviews && <ReviewRecord topic={topic} subscription={subscription} snapshotAttempt={snapshot.last_attempt_at} review={reviews[topic]} canEdit={canEdit}
      onSaved={(review) => setReviews((current) => ({ ...current, [topic]: review }))} />;
  }
  return <section className="card account-form">
    <h2>Technical evidence review</h2>
    <p>Use these shared Azure evidence topics to prepare for HIPAA, SOC 2, ISO 27001, and PCI DSS review. Framework-specific control catalogs are pending.</p>
    {!reviews && !reviewError && <p role="status">Loading review records…</p>}
    {reviewError && <p className="error" role="alert">{reviewError}</p>}
    {snapshot.status === "synced" && snapshot.last_success_at && <p>Last complete collection {snapshotTime(snapshot.last_success_at)}.</p>}
    {snapshot.status !== "synced" && <p>{snapshot.last_success_at
      ? `Review uses retained evidence from ${snapshotTime(snapshot.last_success_at)}.`
      : "A complete collection is unavailable. Any findings shown come from incomplete evidence."}</p>}
    {snapshot.limitations?.length > 0 && <details>
      <summary>Collection limitations</summary>
      <ul>{snapshot.limitations.map((limit) => <li key={limit}>{limit}</li>)}</ul>
    </details>}
    <ul className="design-list">
      {Object.entries(THEMES).map(([topic, { name, codes }]) => {
        const findings = (snapshot.findings || []).filter(({ code, source }) =>
          codes.includes(code) && ["azure_configuration", "azure_network_snapshot"].includes(source));
        return <li key={topic}>
          <strong>{name}</strong>
          {findings.length ? <>
            <span>Review required · {findings.length} saved observations</span>
            <details><summary>Review evidence</summary>
              <ul>{findings.map((finding) => <li key={finding.id}>
                <strong>{finding.title}</strong>
                <span>{finding.resource_id}</span>
                <p>Source <code>{finding.source}</code> · Rule <code>{finding.code}</code>{finding.observed_at && ` · Observed ${snapshotTime(finding.observed_at)}`}</p>
                {finding.evidence?.map((item, index) => <p key={index}>{item}</p>)}
              </li>)}</ul>
            </details>
          </> : <span>Unable to validate from saved findings</span>}
          {record(topic)}
        </li>;
      })}
      <li><strong>Scope and operating procedures</strong><span>Manual review required</span>{record("scope")}</li>
    </ul>
  </section>;
}

export default function ComplianceWorkspace({ canEdit = false }) {
  return <AzureSnapshotWorkspace title="Compliance evidence"
    description="Review technical observations for the selected subscription."
    canRefresh={false} loadSnapshot={getAzureSecurity}>
    {(snapshot, subscription) => snapshot && <EvidenceReview snapshot={snapshot} subscription={subscription} canEdit={canEdit} />}
  </AzureSnapshotWorkspace>;
}
