import { useEffect, useState } from "react";
import { getAzureBackupEvidence, getAzureRecoveryObjectives, saveAzureRecoveryObjectives } from "../services/api";
import AzureSnapshotWorkspace, { displayLabel, snapshotTime } from "./AzureSnapshotWorkspace";

const JOB_FIELDS = [
  ["entityFriendlyName", "Resource"], ["operation", "Operation"], ["status", "Status"],
  ["startTime", "Started"], ["endTime", "Ended"],
];
const ITEM_FIELDS = [
  ["friendlyName", "Resource"], ["protectionState", "Protection"], ["protectionStatus", "Health"],
  ["lastBackupStatus", "Last backup"], ["lastBackupTime", "Backup time"],
  ["lastRecoveryPoint", "Recovery point"], ["policyId", "Policy"],
];

const POLICY_FIELDS = [
  ["name", "Policy"], ["backupManagementType", "Management type"], ["retention", "Retention"],
];
const REPLICATION_FIELDS = [
  ["friendlyName", "Resource"], ["protectionState", "Protection"], ["replicationHealth", "Replication health"],
  ["lastRecoveryPointReceived", "Last recovery point received"],
];
const MAX_RPO_HOURS = 8760;
const MAX_RTO_MINUTES = 525600;

export function compareRecoveryEvidence(vault, retrievedAt, rpoHours, rtoMinutes) {
  const retrieved = Date.parse(retrievedAt);
  const pointLimit = rpoHours * 60 * 60 * 1000;
  const durationLimit = rtoMinutes * 60 * 1000;
  const points = vault.protected_items.rows.map((item) => retrieved - Date.parse(item.lastRecoveryPoint))
    .filter((age) => Number.isFinite(age) && age >= 0);
  const restores = vault.jobs.rows.filter((job) =>
    job.operation?.toLowerCase() === "restore" && job.status?.toLowerCase() === "completed")
    .map((job) => Date.parse(job.endTime) - Date.parse(job.startTime))
    .filter((duration) => Number.isFinite(duration) && duration >= 0);
  return {
    recoveryPoints: points.length, pointsOutside: points.filter((age) => age > pointLimit).length,
    restoreJobs: restores.length, restoresOutside: restores.filter((duration) => duration > durationLimit).length,
  };
}

function RecoveryObjectives({ vaults, retrievedAt, subscription, canEdit }) {
  const [rpoHours, setRpoHours] = useState("");
  const [rtoMinutes, setRtoMinutes] = useState("");
  const [saved, setSaved] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const rpo = Number(rpoHours);
  const rto = Number(rtoMinutes);
  const usable = Number.isInteger(rpo) && rpo >= 1 && rpo <= MAX_RPO_HOURS
    && Number.isInteger(rto) && rto >= 1 && rto <= MAX_RTO_MINUTES;

  useEffect(() => {
    let active = true;
    getAzureRecoveryObjectives(subscription).then((objectives) => {
      if (!active || !objectives) return;
      setSaved(objectives);
      setRpoHours(String(objectives.rpo_hours));
      setRtoMinutes(String(objectives.rto_minutes));
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") setError(failure.message);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [subscription]);

  async function save(event) {
    event.preventDefault();
    if (!canEdit || !usable) return;
    setError("");
    setFeedback("");
    setSaving(true);
    try {
      const objectives = await saveAzureRecoveryObjectives(subscription, { rpo_hours: rpo, rto_minutes: rto });
      setSaved(objectives);
      setFeedback("Recovery objectives saved.");
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setSaving(false);
    }
  }

  return <section className="card account-form">
    <h3>Recovery objectives review</h3>
    <p>Compare observed recovery point age and completed restore job duration with your targets. Application recovery and unobserved resources require further evidence.</p>
    {loading && <p role="status">Loading saved objectives…</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {saved && <p>Saved targets for this subscription: {saved.rpo_hours} hours RPO and {saved.rto_minutes} minutes RTO.</p>}
    {!loading && !error && !saved && <p>No recovery objectives are saved for this subscription.</p>}
    <form className="account-form" onSubmit={save}>
      <fieldset disabled={loading || saving}>
        <legend>Comparison targets</legend>
        <div className="grid">
          <label>Recovery point objective (hours)<input type="number" min="1" max={MAX_RPO_HOURS} step="1" required
            value={rpoHours} onChange={(event) => setRpoHours(event.target.value)} /></label>
          <label>Recovery time objective (minutes)<input type="number" min="1" max={MAX_RTO_MINUTES} step="1" required
            value={rtoMinutes} onChange={(event) => setRtoMinutes(event.target.value)} /></label>
        </div>
        {canEdit && <button type="submit" disabled={!usable}>{saving ? "Saving…" : "Save recovery objectives"}</button>}
      </fieldset>
    </form>
    {feedback && <p role="status">{feedback}</p>}
    {usable && vaults.length === 0 && <p>Vault evidence is unavailable for comparison.</p>}
    {usable && vaults.length > 0 && <ul aria-label="Observed recovery comparison">
      {vaults.map((vault) => {
        const evidence = compareRecoveryEvidence(vault, retrievedAt, rpo, rto);
        return <li key={vault.id}>
          <strong>{vault.name}</strong>
          <p>{evidence.recoveryPoints
            ? `${evidence.pointsOutside} of ${evidence.recoveryPoints} observed recovery points exceed the age target.`
            : "Recovery point timestamps are unavailable."}</p>
          <p>{evidence.restoreJobs
            ? `${evidence.restoresOutside} of ${evidence.restoreJobs} completed restore jobs exceed the duration target.`
            : "Completed restore job timing is unavailable."}</p>
        </li>;
      })}
    </ul>}
  </section>;
}

function EvidenceTable({ title, evidence, fields }) {
  return <section className="account-form">
    <h4>{title}</h4>
    <p>{displayLabel(evidence.status)}{evidence.truncated && " | First page only"}</p>
    {evidence.rows.length > 0 ? <div className="design-table">
      <table className="table" aria-label={title}>
        <thead><tr>{fields.map(([key, label]) => <th key={key} scope="col">{label}</th>)}</tr></thead>
        <tbody>{evidence.rows.map((row, index) => <tr key={index}>{fields.map(([key]) =>
          <td key={key}>{row[key] || "Unavailable"}</td>)}</tr>)}</tbody>
      </table>
    </div> : <p>{evidence.status === "synced" ? "Azure returned no records." : "Evidence unavailable."}</p>}
  </section>;
}

export default function AzureBackupWorkspace({ canEdit = false }) {
  return <AzureSnapshotWorkspace title="Backup and recovery"
    description="Review Azure Recovery Services vault evidence for a configured subscription."
    canRefresh={false} loadSnapshot={getAzureBackupEvidence}>
    {(snapshot, subscription) => <>
      <RecoveryObjectives vaults={snapshot?.vaults || []} retrievedAt={snapshot?.retrieved_at}
        subscription={subscription} canEdit={canEdit} />
      {snapshot && <section className="card account-form">
        <h2>Recovery Services evidence</h2>
        {snapshot.status === "no_vaults_in_inventory" && <p>No Recovery Services vaults were found in the saved inventory.</p>}
        {snapshot.retrieved_at && <p>Retrieved {snapshotTime(snapshot.retrieved_at)}</p>}
        {snapshot.limitations?.length > 0 && <ul>{snapshot.limitations.map((item) => <li key={item}>{item}</li>)}</ul>}
        {snapshot.vaults.map((vault) => <section key={vault.id} className="card account-form">
          <h3>{vault.name}</h3>
          <EvidenceTable title="Backup and restore jobs" evidence={vault.jobs} fields={JOB_FIELDS} />
          <EvidenceTable title="Protected items" evidence={vault.protected_items} fields={ITEM_FIELDS} />
          <EvidenceTable title="Retention policies" evidence={vault.policies} fields={POLICY_FIELDS} />
          {vault.replication_items && <EvidenceTable title="Site Recovery replication"
            evidence={vault.replication_items} fields={REPLICATION_FIELDS} />}
        </section>)}
      </section>}
    </>}
  </AzureSnapshotWorkspace>;
}
