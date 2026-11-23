import { getAzureBackupEvidence } from "../services/api";
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

export default function AzureBackupWorkspace() {
  return <AzureSnapshotWorkspace title="Backup and recovery"
    description="Review Azure Recovery Services vault evidence for a configured subscription."
    canRefresh={false} loadSnapshot={getAzureBackupEvidence}>
    {(snapshot) => snapshot && <section className="card account-form">
      <h2>Recovery Services evidence</h2>
      {snapshot.status === "no_vaults_in_inventory" && <p>No Recovery Services vaults were found in the saved inventory.</p>}
      {snapshot.retrieved_at && <p>Retrieved {snapshotTime(snapshot.retrieved_at)}</p>}
      {snapshot.limitations?.length > 0 && <ul>{snapshot.limitations.map((item) => <li key={item}>{item}</li>)}</ul>}
      {snapshot.vaults.map((vault) => <section key={vault.id} className="card account-form">
        <h3>{vault.name}</h3>
        <EvidenceTable title="Backup and restore jobs" evidence={vault.jobs} fields={JOB_FIELDS} />
        <EvidenceTable title="Protected items" evidence={vault.protected_items} fields={ITEM_FIELDS} />
      </section>)}
    </section>}
  </AzureSnapshotWorkspace>;
}
