import { useEffect, useState } from "react";
import { getGovernanceComplianceSummary, getGovernanceSecuritySummary, listArchitectures } from "../services/api";

const FRAMEWORKS = ["HIPAA"];

export default function GovernanceWorkspace() {
  const [architectures, setArchitectures] = useState([]);
  const [architectureId, setArchitectureId] = useState("");
  const [frameworks] = useState(FRAMEWORKS);
  const [summary, setSummary] = useState(null);
  const [securitySummary, setSecuritySummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [securityLoading, setSecurityLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadArchitectures() {
      try {
        const items = await listArchitectures();
        setArchitectures(items);
        if (items[0]?.id) setArchitectureId(items[0].id);
      } catch (e) {
        setError(e.message || "Failed to load architectures");
      }
    }
    loadArchitectures();
  }, []);

  useEffect(() => {
    setSummary(null);
    setSecuritySummary(null);
  }, [architectureId]);

  async function runCompliance() {
    if (!architectureId) return;
    setLoading(true);
    setError("");
    try {
      const next = await getGovernanceComplianceSummary(architectureId, { frameworks });
      setSummary(next);
    } catch (e) {
      setError(e.message || "Compliance request failed");
    } finally {
      setLoading(false);
    }
  }

  async function runSecurityAssessment() {
    if (!architectureId) return;
    setSecurityLoading(true);
    setError("");
    try {
      const next = await getGovernanceSecuritySummary(architectureId, {});
      setSecuritySummary(next);
    } catch (e) {
      setError(e.message || "Security assessment request failed");
    } finally {
      setSecurityLoading(false);
    }
  }

  return (
    <section className="workspace-panel">
      <div className="workspace-header">
        <div>
          <div className="workspace-eyebrow">Governance</div>
          <h1>Governance / Security / Compliance</h1>
          <p>Legacy compliance engine validation surfaced in the platform governance workspace.</p>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      <section className="card workspace-stack">
        <div className="toolbar-row">
          <select value={architectureId} onChange={(e) => setArchitectureId(e.target.value)}>
            {architectures.length === 0 ? (
              <option value="">No architectures</option>
            ) : (
              architectures.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)
            )}
          </select>
          <button onClick={runCompliance} disabled={!architectureId || loading}>{loading ? "Loading..." : "Run HIPAA Assessment"}</button>
          <button onClick={runSecurityAssessment} disabled={!architectureId || securityLoading}>{securityLoading ? "Loading..." : "Run Security Assessment"}</button>
        </div>

        <div className="toolbar-row" role="group" aria-label="Compliance frameworks">
          <span className="pill">Framework: HIPAA</span>
          <span className="pill">Source: legacy_compliance_engine</span>
        </div>

        {!summary && !securitySummary ? (
          <div className="empty">Run compliance and/or security assessment to load governance results.</div>
        ) : (
          <>
            {summary && (
              <>
                <div className="platform-grid">
                  <article className="platform-card">
                    <h3>Governance State</h3>
                    <div className="platform-value" style={{ fontSize: 22 }}>{summary.state}</div>
                    <p>Assessment execution state from the integrated HIPAA governance adapter.</p>
                  </article>
                  <article className="platform-card">
                    <h3>HIPAA Result</h3>
                    <div className="platform-value" style={{ fontSize: 22 }}>
                      {summary.compliant === null ? "n/a" : summary.compliant ? "compliant" : "non-compliant"}
                    </div>
                    <p>Calculated from HIPAA controls, findings, and severity-weighted scoring.</p>
                  </article>
                  <article className="platform-card">
                    <h3>Overall Score</h3>
                    <div className="platform-value" style={{ fontSize: 22 }}>{summary.overall_score ?? "n/a"}</div>
                    <p>Compliance score derived from critical/high/medium/low finding counts.</p>
                  </article>
                  <article className="platform-card">
                    <h3>Azure Connection</h3>
                    <div className="platform-value" style={{ fontSize: 22 }}>{summary.azure_connection_state || "unknown"}</div>
                    <p>{summary.live_connected ? "Authenticated Azure context available." : "Controlled not-configured/unavailable Azure state."}</p>
                  </article>
                </div>

                {summary.message ? <div className="pill warn">{summary.message}</div> : null}
                {summary.azure_connection_message ? <div className="pill">{summary.azure_connection_message}</div> : null}

                <section className="card">
                  <div className="status-list">
                    <div><strong>Frameworks:</strong> {summary.frameworks.length ? summary.frameworks.join(", ") : "none"}</div>
                    <div><strong>Evaluated Resources:</strong> {summary.evaluated_resources}</div>
                    <div><strong>Total Findings:</strong> {summary.total_findings ?? summary.violations.length}</div>
                    <div><strong>Critical:</strong> {summary.critical_count ?? 0}</div>
                    <div><strong>High:</strong> {summary.high_count ?? 0}</div>
                    <div><strong>Medium:</strong> {summary.medium_count ?? 0}</div>
                    <div><strong>Low:</strong> {summary.low_count ?? 0}</div>
                    <div><strong>Recommendations:</strong> {summary.recommendations.length}</div>
                  </div>
                </section>

                <section className="card">
                  <div className="card-title"><h2>Framework Scores</h2></div>
                  {!summary.framework_results || summary.framework_results.length === 0 ? (
                    <div className="empty">No framework score rows returned.</div>
                  ) : (
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Framework</th>
                          <th>Status</th>
                          <th>Score</th>
                          <th>Critical</th>
                          <th>High</th>
                          <th>Medium</th>
                          <th>Low</th>
                        </tr>
                      </thead>
                      <tbody>
                        {summary.framework_results.map((row, idx) => (
                          <tr key={`f-${idx}`}>
                            <td>{row.framework}</td>
                            <td>{row.status}</td>
                            <td>{row.score}</td>
                            <td>{row.critical_count}</td>
                            <td>{row.high_count}</td>
                            <td>{row.medium_count}</td>
                            <td>{row.low_count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </section>

                <section className="card">
                  <div className="card-title"><h2>HIPAA Findings</h2></div>
                  {!summary.findings || summary.findings.length === 0 ? (
                    <div className="empty">No HIPAA findings detected for this architecture.</div>
                  ) : (
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Severity</th>
                          <th>Control</th>
                          <th>Resource</th>
                          <th>Finding</th>
                          <th>Remediation</th>
                        </tr>
                      </thead>
                      <tbody>
                        {summary.findings.map((item, idx) => (
                          <tr key={`${item.finding_id}-${idx}`}>
                            <td>{item.severity}</td>
                            <td>{item.control_id}</td>
                            <td>{item.resource_name || item.resource_type || "architecture"}</td>
                            <td>{item.message}</td>
                            <td>{item.remediation}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </section>

                <section className="card">
                  <div className="card-title"><h2>Recommendations</h2></div>
                  {summary.recommendations.length === 0 ? (
                    <div className="empty">No recommendations at this stage.</div>
                  ) : (
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Guidance</th>
                        </tr>
                      </thead>
                      <tbody>
                        {summary.recommendations.map((item, idx) => (
                          <tr key={`r-${idx}`}>
                            <td>{item}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </section>
              </>
            )}

            {securitySummary && (
              <section className="card">
                <div className="card-title"><h2>Security Assessment</h2></div>
                <>
                  <div className="platform-grid">
                    <article className="platform-card">
                      <h3>Security State</h3>
                      <div className="platform-value" style={{ fontSize: 22 }}>{securitySummary.state}</div>
                      <p>Security checks from legacy rule engine.</p>
                    </article>
                    <article className="platform-card">
                      <h3>Risk Level / Score</h3>
                      <div className="platform-value" style={{ fontSize: 22 }}>{securitySummary.risk_level} / {securitySummary.security_score}</div>
                      <p>Risk calculated from findings and severity.</p>
                    </article>
                    <article className="platform-card">
                      <h3>Security Source</h3>
                      <div className="platform-value" style={{ fontSize: 22 }}>{securitySummary.source}</div>
                      <p>Expected: legacy_security_engine.</p>
                    </article>
                  </div>

                  <div className="status-list">
                    <div><strong>Findings:</strong> {securitySummary.total_findings} total (critical: {securitySummary.critical_count}, high: {securitySummary.high_count}, medium: {securitySummary.medium_count}, low: {securitySummary.low_count})</div>
                    <div><strong>Secrets:</strong> {securitySummary.secrets_count}</div>
                    <div><strong>Evaluated Resources:</strong> {securitySummary.evaluated_resources}</div>
                  </div>

                  <div className="card-title"><h2>Security Findings</h2></div>
                  {securitySummary.findings.length === 0 ? (
                    <div className="empty">No security findings detected.</div>
                  ) : (
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Title</th>
                          <th>Severity</th>
                          <th>Resource</th>
                          <th>Category</th>
                          <th>Recommendation</th>
                        </tr>
                      </thead>
                      <tbody>
                        {securitySummary.findings.map((item, idx) => (
                          <tr key={`${item.id}-${idx}`}>
                            <td>{item.title}</td>
                            <td>{item.severity}</td>
                            <td>{item.resource_name}</td>
                            <td>{item.category || "n/a"}</td>
                            <td>{item.recommendation}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}

                  <div className="card-title"><h2>Potential Secrets</h2></div>
                  {securitySummary.secrets.length === 0 ? (
                    <div className="empty">No potential secrets detected in resource configuration.</div>
                  ) : (
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Type</th>
                          <th>Severity</th>
                          <th>Resource</th>
                          <th>Location</th>
                          <th>Description</th>
                        </tr>
                      </thead>
                      <tbody>
                        {securitySummary.secrets.map((item, idx) => (
                          <tr key={`${item.id}-${idx}`}>
                            <td>{item.type}</td>
                            <td>{item.severity}</td>
                            <td>{item.resource_name}</td>
                            <td>{item.location}</td>
                            <td>{item.description}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </>
              </section>
            )}
          </>
        )}
      </section>
    </section>
  );
}
