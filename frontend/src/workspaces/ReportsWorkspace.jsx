import { useEffect, useState } from "react";
import { getArchitectureExecutiveReport, listArchitectures } from "../services/api";

function downloadJson(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function ReportsWorkspace() {
  const [architectures, setArchitectures] = useState([]);
  const [architectureId, setArchitectureId] = useState("");
  const [provider, setProvider] = useState("auto");
  const [includeActualCost, setIncludeActualCost] = useState(true);
  const [report, setReport] = useState(null);
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
    setReport(null);
  }, [architectureId]);

  async function generateReport() {
    if (!architectureId) return;
    setLoading(true);
    setError("");

    try {
      const payload = {
        include_actual_cost: includeActualCost,
      };
      if (provider !== "auto") payload.provider = provider;

      const next = await getArchitectureExecutiveReport(architectureId, payload);
      setReport(next);
    } catch (e) {
      setError(e.message || "Failed to generate executive report");
    } finally {
      setLoading(false);
    }
  }

  function exportReport() {
    if (!report) return;
    const safeName = (report.architecture?.name || "architecture").toLowerCase().replace(/\s+/g, "-");
    downloadJson(`monitorai-v215-report-${safeName}.json`, report);
  }

  return (
    <section className="workspace-panel">
      <div className="workspace-header">
        <div>
          <div className="workspace-eyebrow">Reports</div>
          <h1>Executive Reports</h1>
          <p>Generate a cross-domain architecture report from live platform signals and intelligence output.</p>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      <section className="card workspace-stack">
        <div className="toolbar-row">
          <select value={architectureId} onChange={(e) => setArchitectureId(e.target.value)}>
            {architectures.length === 0 ? (
              <option value="">No architectures</option>
            ) : (
              architectures.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))
            )}
          </select>
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="auto">Auto provider selection</option>
            <option value="openai">OpenAI</option>
            <option value="gemini">Gemini</option>
            <option value="deterministic_fallback">Deterministic fallback</option>
          </select>
          <label>
            <input
              type="checkbox"
              checked={includeActualCost}
              onChange={(e) => setIncludeActualCost(e.target.checked)}
            />
            Include actual billed cost
          </label>
          <button onClick={generateReport} disabled={!architectureId || loading}>
            {loading ? "Generating..." : "Generate Report"}
          </button>
          <button onClick={exportReport} disabled={!report}>Export JSON</button>
        </div>

        {!report ? (
          <div className="empty">Generate a report to view architecture-level executive insights.</div>
        ) : (
          <>
            <div className="platform-grid">
              <article className="platform-card">
                <h3>Findings</h3>
                <div className="platform-value" style={{ fontSize: 24 }}>{report.highlights.findings_count}</div>
                <p>AI findings from architecture, monitoring, security, and cost context.</p>
              </article>
              <article className="platform-card">
                <h3>Incidents</h3>
                <div className="platform-value" style={{ fontSize: 24 }}>{report.highlights.incidents_count}</div>
                <p>Generated from monitoring signals through the legacy incident engine.</p>
              </article>
              <article className="platform-card">
                <h3>Monthly Estimated Cost</h3>
                <div className="platform-value" style={{ fontSize: 24 }}>${report.highlights.monthly_estimated_cost}</div>
                <p>Pricing source: {report.cost_estimate.pricing_source}</p>
              </article>
            </div>

            <section className="card">
              <div className="status-list">
                <div><strong>Generated:</strong> {report.generated_at}</div>
                <div><strong>Architecture:</strong> {report.architecture.name}</div>
                <div><strong>Monitoring state:</strong> {report.monitoring.state}</div>
                <div><strong>Security risk:</strong> {report.highlights.security_risk_level}</div>
                <div><strong>Intelligence provider used:</strong> {report.highlights.provider_used}</div>
                <div><strong>Actual cost availability:</strong> {report.highlights.actual_cost_available ? "available" : "unavailable"}</div>
              </div>
              {report.notes?.length ? (
                <div className="status-list" style={{ marginTop: 12 }}>
                  {report.notes.map((note, idx) => (
                    <div key={`${idx}-${note}`}><strong>Note:</strong> {note}</div>
                  ))}
                </div>
              ) : null}
            </section>

            <section className="card">
              <div className="card-title"><h2>Intelligence Recommendations</h2></div>
              {report.intelligence.recommendations.length === 0 ? (
                <div className="empty">No recommendations generated for current context.</div>
              ) : (
                <table className="table">
                  <thead>
                    <tr>
                      <th>Title</th>
                      <th>Severity</th>
                      <th>Category</th>
                      <th>Recommendation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.intelligence.recommendations.map((item, idx) => (
                      <tr key={`${item.id}-${idx}`}>
                        <td>{item.title}</td>
                        <td>{item.severity}</td>
                        <td>{item.category}</td>
                        <td>{item.recommendation}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            <section className="card">
              <div className="card-title"><h2>Incident Signals</h2></div>
              {report.incidents.incident_count === 0 ? (
                <div className="empty">No incidents generated from current monitoring signals.</div>
              ) : (
                <table className="table">
                  <thead>
                    <tr>
                      <th>Title</th>
                      <th>Severity</th>
                      <th>Status</th>
                      <th>Resource</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.incidents.incidents.map((item) => (
                      <tr key={item.incident_id}>
                        <td>{item.title}</td>
                        <td>{item.severity}</td>
                        <td>{item.status}</td>
                        <td>{item.resource_name || "n/a"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          </>
        )}
      </section>
    </section>
  );
}
