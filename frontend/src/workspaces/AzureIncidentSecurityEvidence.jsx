import { useEffect, useState } from "react";
import { getAzureIncidentSecurityEvidence, getAzureSecurity, linkAzureIncidentSecurityEvidence } from "../services/api";
import { displayLabel, snapshotTime } from "./AzureSnapshotWorkspace";

export default function AzureIncidentSecurityEvidence({ subscription, incidentId, canEdit }) {
  const [links, setLinks] = useState(null);
  const [snapshot, setSnapshot] = useState(null);
  const [readCount, setReadCount] = useState(0);
  const [findingId, setFindingId] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [snapshotError, setSnapshotError] = useState("");
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState("");

  useEffect(() => {
    let active = true;
    getAzureIncidentSecurityEvidence(subscription, incidentId).then((data) => {
      if (active) setLinks(data);
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") setError(failure.message);
    });
    if (canEdit) {
      getAzureSecurity(subscription).then((data) => {
        if (active) setSnapshot(data);
      }).catch((failure) => {
        if (active && failure.name !== "AbortError") setSnapshotError(failure.message);
      });
    }
    return () => { active = false; };
  }, [subscription, incidentId, canEdit, readCount]);

  function reload() {
    setLinks(null);
    setSnapshot(null);
    setError("");
    setSnapshotError("");
    setFeedback("");
    setFindingId("");
    setReadCount((count) => count + 1);
  }

  const linkedIds = new Set((links || []).map((link) => link.finding_id));
  const normalizedQuery = query.trim().toLowerCase();
  const choices = (snapshot?.findings || []).filter((finding) =>
    /^[0-9a-f]{64}$/.test(finding.id || "") && !linkedIds.has(finding.id) &&
    (!normalizedQuery || [finding.title, finding.code, finding.resource_id]
      .some((field) => field?.toLowerCase().includes(normalizedQuery))));
  const selected = choices.some((finding) => finding.id === findingId) ? findingId : "";

  async function linkFinding(event) {
    event.preventDefault();
    if (!selected || !snapshot?.last_success_at) return;
    setSaving(true);
    setError("");
    setFeedback("");
    try {
      const linked = await linkAzureIncidentSecurityEvidence(subscription, incidentId, selected, snapshot.last_success_at);
      setLinks((current) => [
        ...(current || []).filter((item) => item.finding_id !== linked.finding_id), linked,
      ]);
      setFindingId("");
      setFeedback("Security evidence linked.");
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setSaving(false);
    }
  }

  return <section className="account-form">
    <h3>Linked Security evidence</h3>
    <div><button type="button" className="dismiss" disabled={saving} onClick={reload}>Reload Security evidence</button></div>
    {error && <p className="error" role="alert">{error}</p>}
    {feedback && <p role="status">{feedback}</p>}
    {!links && !error && <p role="status">Loading linked evidence...</p>}
    {links && (links.length > 0 ? <ul className="design-list">{links.map((link) => (
      <li key={link.finding_id}>
        <strong>{link.title}</strong>
        <span>{displayLabel(link.source)} / {link.code}</span>
        {link.resource_id && <span>{link.resource_id}</span>}
        <dl className="design-meta">
          {link.observed_at && <div><dt>Observed</dt><dd>{snapshotTime(link.observed_at)}</dd></div>}
          <div><dt>Security snapshot</dt><dd>{snapshotTime(link.collected_at)}</dd></div>
          <div><dt>Linked</dt><dd>{snapshotTime(link.linked_at)}</dd></div>
          <div><dt>Finding reference</dt><dd><code>{link.finding_id}</code></dd></div>
        </dl>
        {link.evidence.length > 0 && <details><summary>Saved finding evidence</summary>
          <ul>{link.evidence.map((line, index) => <li key={index}>{line}</li>)}</ul>
        </details>}
      </li>
    ))}</ul> : <p>No Security evidence linked to this incident.</p>)}
    {canEdit && <>
      {snapshotError && <p className="error" role="alert">{snapshotError}</p>}
      {!snapshot && !snapshotError && <p role="status">Loading saved Security findings...</p>}
      {snapshot && !snapshot.last_success_at && <p>A completed Security snapshot is required to link evidence.</p>}
      {links && snapshot?.last_success_at && <form className="account-form" onSubmit={linkFinding}>
        <p>{snapshot.status === "synced" ? "Saved Security snapshot" : "Retained Security snapshot"} {snapshotTime(snapshot.last_success_at)}.</p>
        <fieldset disabled={saving}>
          <label>Filter saved findings<input value={query} onChange={(event) => setQuery(event.target.value)} /></label>
          <label>Saved Security finding<select value={selected} onChange={(event) => setFindingId(event.target.value)} required>
            <option value="">Choose a finding</option>
            {choices.map((item) => <option key={item.id} value={item.id}>{item.title} ({item.resource_id || item.code})</option>)}
          </select></label>
          {!choices.length && <p>No unlinked findings match this filter.</p>}
          <div><button type="submit" disabled={!selected}>{saving ? "Linking..." : "Link Security finding"}</button></div>
        </fieldset>
      </form>}
    </>}
  </section>;
}
