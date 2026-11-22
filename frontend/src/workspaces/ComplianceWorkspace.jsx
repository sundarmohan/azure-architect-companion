import { getAzureSecurity } from "../services/api";
import AzureSnapshotWorkspace, { snapshotTime } from "./AzureSnapshotWorkspace";

const THEMES = {
  transport: { name: "Protected transport", codes: ["storage_http_allowed", "storage_legacy_tls"] },
  storage: { name: "Storage access and encryption", codes: ["storage_public_blob_allowed", "sql_tde_disabled"] },
  network: { name: "Network access restrictions", codes: ["vault_public_network", "sql_public_network", "nsg_external_inbound"] },
  recovery: { name: "Key recovery safeguards", codes: ["vault_purge_unprotected"] },
};

function EvidenceReview({ snapshot }) {
  return <section className="card account-form">
    <h2>Technical evidence review</h2>
    <p>Use these shared Azure evidence topics to prepare for HIPAA, SOC 2, ISO 27001, and PCI DSS review. Framework-specific control catalogs are pending.</p>
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
        </li>;
      })}
      <li><strong>Scope and operating procedures</strong><span>Manual review required</span></li>
    </ul>
  </section>;
}

export default function ComplianceWorkspace() {
  return <AzureSnapshotWorkspace title="Compliance evidence"
    description="Review technical observations for the selected subscription."
    canRefresh={false} loadSnapshot={getAzureSecurity}>
    {(snapshot) => snapshot && <EvidenceReview snapshot={snapshot} />}
  </AzureSnapshotWorkspace>;
}
