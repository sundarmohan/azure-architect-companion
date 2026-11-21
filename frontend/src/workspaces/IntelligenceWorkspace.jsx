import { useEffect, useState } from "react";
import { getArchitectureIntelligenceAnalysis, listArchitectures } from "../services/api";

function sourceSetFromResult(result) {
  const sources = new Set();
  (result?.observed_facts || []).forEach((item) => {
    if (item?.source) sources.add(String(item.source));
  });
  (result?.findings || []).forEach((item) => {
    if (item?.source) sources.add(String(item.source));
  });
  (result?.recommendations || []).forEach((item) => {
    if (item?.source) sources.add(String(item.source));
  });
  (result?.risks || []).forEach((item) => {
    if (item?.source) sources.add(String(item.source));
  });
  return sources;
}

function pipelineSources(result) {
  const sources = sourceSetFromResult(result);
  const provider = result?.provider || "deterministic_fallback";
  const providerState = result?.error_state || "configured_or_fallback";
  const hasMonitoring =
    sources.has("monitoring_summary") ||
    (result?.incident_correlations || []).length > 0 ||
    (result?.limitations || []).some((item) => String(item).toLowerCase().includes("monitoring"));
  const hasIncidents =
    sources.has("incident_summary") ||
    (result?.incident_correlations || []).length > 0 ||
    (result?.rca || []).length > 0;
  const hasGovernance =
    sources.has("governance_security") ||
    (result?.findings || []).some((item) => item?.category === "security_design");
  const hasCost =
    sources.has("cost_estimate") ||
    (result?.findings || []).some((item) => item?.category === "cost_optimization");

  return [
    { label: "Architecture", used: true, detail: "resources/relationships/hierarchy" },
    { label: "Monitoring", used: hasMonitoring, detail: hasMonitoring ? "summary/signals consumed" : "not available" },
    { label: "Incidents", used: hasIncidents, detail: hasIncidents ? "legacy incident summary/correlation" : "no incident context" },
    { label: "Security/Governance", used: hasGovernance, detail: hasGovernance ? "legacy security/compliance context" : "no security/governance signal" },
    { label: "Cost", used: hasCost, detail: hasCost ? "estimated/actual availability context" : "cost context unavailable" },
    { label: "AI Provider/Fallback", used: true, detail: `${provider} (${providerState})` },
  ];
}

export default function IntelligenceWorkspace() {
  const [architectures, setArchitectures] = useState([]);
  const [architectureId, setArchitectureId] = useState("");
  const [provider, setProvider] = useState("auto");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
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
    setResult(null);
  }, [architectureId]);

  async function analyzeArchitecture() {
    if (!architectureId) return;
    setLoading(true);
    setError("");
    try {
      const payload = provider === "auto" ? {} : { provider };
      const next = await getArchitectureIntelligenceAnalysis(architectureId, payload);
      setResult(next);
    } catch (e) {
      setError(e.message || "Intelligence analysis failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="workspace-panel">
      <div className="workspace-header">
        <div>
          <div className="workspace-eyebrow">Intelligence</div>
          <h1>Intelligence / AI</h1>
          <p>Deterministic architecture intelligence analysis with explainable findings and recommendations.</p>
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
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="auto">Auto (configured provider then fallback)</option>
            <option value="openai">OpenAI</option>
            <option value="gemini">Gemini</option>
            <option value="deterministic_fallback">Deterministic fallback</option>
          </select>
          <button onClick={analyzeArchitecture} disabled={!architectureId || loading}>{loading ? "Loading..." : "Analyze Architecture"}</button>
        </div>

        {!result ? (
          <div className="empty">Run analysis to generate intelligence findings and recommendations.</div>
        ) : (
          <>
            <div className="platform-grid">
              <article className="platform-card">
                <h3>Analysis State</h3>
                <div className="platform-value" style={{ fontSize: 22 }}>{result.status || result.state}</div>
                <p>Controlled execution state for deterministic analysis.</p>
              </article>
              <article className="platform-card">
                <h3>Overall Assessment</h3>
                <div className="platform-value" style={{ fontSize: 18 }}>{result.overall_assessment}</div>
                <p>Summary generated from architecture signals only.</p>
              </article>
              <article className="platform-card">
                <h3>Findings</h3>
                <div className="platform-value" style={{ fontSize: 22 }}>{result.finding_count}</div>
                <p>Source: {result.source} / Provider: {result.provider || "deterministic_fallback"}</p>
              </article>
            </div>

            {result.message ? <div className="pill warn">{result.message}</div> : null}
            {result.error_state ? <div className="pill error">Provider state: {result.error_state}</div> : null}

            <section className="card">
              <div className="status-list">
                <div><strong>Severity Summary:</strong> critical={result.severity_summary.critical || 0}, high={result.severity_summary.high || 0}, medium={result.severity_summary.medium || 0}, low={result.severity_summary.low || 0}</div>
                <div><strong>Recommendations:</strong> {result.recommendations.length}</div>
                <div><strong>Analysis Confidence:</strong> {typeof result.analysis_confidence === "number" ? `${Math.round(result.analysis_confidence * 100)}%` : "n/a"}</div>
                <div><strong>Generated:</strong> {result.generated_at || "n/a"}</div>
              </div>
            </section>

            <section className="card">
              <div className="card-title"><h2>Pipeline Data Sources</h2></div>
              <div className="status-list">
                {pipelineSources(result).map((item) => (
                  <div key={item.label}><strong>{item.label}:</strong> {item.used ? "used" : "unavailable"} ({item.detail})</div>
                ))}
              </div>
            </section>

            <section className="card">
              <div className="card-title"><h2>Observed Facts</h2></div>
              {!result.observed_facts || result.observed_facts.length === 0 ? (
                <div className="empty">No observed facts captured from available architecture signals.</div>
              ) : (
                <table className="table">
                  <thead>
                    <tr>
                      <th>Fact</th>
                      <th>Source</th>
                      <th>Evidence</th>
                      <th>Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.observed_facts.map((item, idx) => (
                      <tr key={`${item.id}-${idx}`}>
                        <td>{item.fact}</td>
                        <td>{item.source}</td>
                        <td>{item.evidence || "n/a"}</td>
                        <td>{typeof item.confidence === "number" ? `${Math.round(item.confidence * 100)}%` : "n/a"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            <section className="card">
              <div className="card-title"><h2>Risks</h2></div>
              {!result.risks || result.risks.length === 0 ? (
                <div className="empty">No risks produced for current context.</div>
              ) : (
                <table className="table">
                  <thead>
                    <tr>
                      <th>Title</th>
                      <th>Priority</th>
                      <th>Explanation</th>
                      <th>Impact</th>
                      <th>Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.risks.map((item, idx) => (
                      <tr key={`${item.id}-${idx}`}>
                        <td>{item.title}</td>
                        <td>{item.priority}</td>
                        <td>{item.explanation}</td>
                        <td>{item.impact}</td>
                        <td>{item.source}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            <section className="card">
              <div className="card-title"><h2>Findings</h2></div>
              {result.findings.length === 0 ? (
                <div className="empty">No findings for current architecture and available signals.</div>
              ) : (
                <table className="table">
                  <thead>
                    <tr>
                      <th>Title</th>
                      <th>Severity</th>
                      <th>Category</th>
                      <th>Rationale</th>
                      <th>Affected</th>
                      <th>Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.findings.map((item, idx) => (
                      <tr key={`${item.id}-${idx}`}>
                        <td>{item.title}</td>
                        <td>{item.severity}</td>
                        <td>{item.category}</td>
                        <td>{item.rationale}</td>
                        <td>{(item.affected_resources || []).join(", ") || "n/a"}</td>
                        <td>{item.source}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            <section className="card">
              <div className="card-title"><h2>Recommendations</h2></div>
              {result.recommendations.length === 0 ? (
                <div className="empty">No recommendations produced for current context.</div>
              ) : (
                <table className="table">
                  <thead>
                    <tr>
                      <th>Title</th>
                      <th>Category</th>
                      <th>Severity</th>
                      <th>Recommendation</th>
                      <th>Rationale</th>
                      <th>Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.recommendations.map((item, idx) => (
                      <tr key={`${item.id}-${idx}`}>
                        <td>{item.title}</td>
                        <td>{item.category}</td>
                        <td>{item.severity}</td>
                        <td>{item.recommendation}</td>
                        <td>{item.rationale}</td>
                        <td>{item.source}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            <section className="card">
              <div className="card-title"><h2>Root Cause Analysis (RCA)</h2></div>
              {!result.rca || result.rca.length === 0 ? (
                <div className="empty">No RCA entries were produced from current monitoring/incident context.</div>
              ) : (
                <table className="table">
                  <thead>
                    <tr>
                      <th>Affected Resource</th>
                      <th>Observed Symptom</th>
                      <th>Related Dependency</th>
                      <th>Probable Cause</th>
                      <th>Impact</th>
                      <th>Recommended Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.rca.map((item, idx) => (
                      <tr key={`${item.id}-${idx}`}>
                        <td>{item.affected_resource}</td>
                        <td>{item.observed_symptom}</td>
                        <td>{item.related_dependency || "n/a"}</td>
                        <td>{item.probable_cause}</td>
                        <td>{item.impact}</td>
                        <td>{item.recommended_action}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            <section className="card">
              <div className="card-title"><h2>Incident Correlation</h2></div>
              {!result.incident_correlations || result.incident_correlations.length === 0 ? (
                <div className="empty">No correlated incidents were available for this analysis window.</div>
              ) : (
                <table className="table">
                  <thead>
                    <tr>
                      <th>Incident</th>
                      <th>Severity</th>
                      <th>Status</th>
                      <th>Resource</th>
                      <th>Monitoring State</th>
                      <th>Correlation Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.incident_correlations.map((item, idx) => (
                      <tr key={`${item.incident_id}-${idx}`}>
                        <td>{item.title}</td>
                        <td>{item.severity}</td>
                        <td>{item.status}</td>
                        <td>{item.resource_name || "n/a"}</td>
                        <td>{item.monitoring_state || "n/a"}</td>
                        <td>{item.correlation_reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            {!!result.limitations?.length && (
              <section className="card">
                <div className="card-title"><h2>Limitations</h2></div>
                <div className="status-list">
                  {result.limitations.map((item, idx) => (
                    <div key={`${idx}-${item}`}>{item}</div>
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </section>
    </section>
  );
}
