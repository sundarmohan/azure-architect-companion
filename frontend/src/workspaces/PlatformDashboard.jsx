import { useEffect, useMemo, useState } from "react";
import {
  getSettingsOverview,
  listAzureSubscriptionInventory,
} from "../services/api";

function card(title, value, subtitle) {
  return { title, value, subtitle };
}

export default function PlatformDashboard({ onOpenArchitectureStudio, onOpenSettings }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [azureIntegration, setAzureIntegration] = useState(null);
  const [subscriptions, setSubscriptions] = useState([]);
  const [summary, setSummary] = useState({
    connectedSubscriptionCount: 0,
    resourceGroupCount: 0,
    resourceCount: 0,
    monitoredResources: 0,
    liveResources: 0,
    activeAlerts: 0,
    activeIncidents: 0,
    unusedResources: 0,
    monthlyWaste: 0,
    hipaaAverageScore: null,
    securityHighRiskCount: 0,
    estimatedMonthlyTotal: 0,
    lastDiscoverySyncAt: null,
  });

  useEffect(() => {
    let mounted = true;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const [overview, inventory] = await Promise.all([
          getSettingsOverview(),
          listAzureSubscriptionInventory(),
        ]);
        if (!mounted) return;
        setAzureIntegration(overview?.azure_integration || null);
        setSubscriptions(inventory || []);

        if (!inventory || inventory.length === 0) {
          setSummary({
            connectedSubscriptionCount: 0,
            resourceGroupCount: 0,
            resourceCount: 0,
            monitoredResources: 0,
            liveResources: 0,
            activeAlerts: 0,
            activeIncidents: 0,
            unusedResources: 0,
            monthlyWaste: 0,
            hipaaAverageScore: null,
            securityHighRiskCount: 0,
            estimatedMonthlyTotal: 0,
            lastDiscoverySyncAt: null,
          });
          return;
        }

        const hipaaScores = inventory
          .map((item) => item.hipaa_score)
          .filter((score) => Number.isFinite(score));

        const next = {
          connectedSubscriptionCount: inventory.filter((item) => item.connection_state === "configured").length,
          resourceGroupCount: inventory.reduce((acc, item) => acc + Number(item.resource_group_count || 0), 0),
          resourceCount: inventory.reduce((acc, item) => acc + Number(item.resource_count || 0), 0),
          monitoredResources: inventory.reduce((acc, item) => acc + Number(item.monitored_resource_count || 0), 0),
          liveResources: inventory.reduce((acc, item) => acc + Number(item.live_resource_count || 0), 0),
          activeAlerts: inventory.reduce((acc, item) => acc + Number(item.active_alert_count || 0), 0),
          activeIncidents: inventory.reduce((acc, item) => acc + Number(item.active_incident_count || 0), 0),
          unusedResources: inventory.reduce((acc, item) => acc + Number(item.unused_resource_count || 0), 0),
          monthlyWaste: inventory.reduce((acc, item) => acc + Number(item.estimated_monthly_waste || 0), 0),
          hipaaAverageScore: hipaaScores.length
            ? Math.round(hipaaScores.reduce((acc, score) => acc + Number(score), 0) / hipaaScores.length)
            : null,
          securityHighRiskCount: inventory.filter((item) => item.security_risk_level === "high").length,
          estimatedMonthlyTotal: inventory.reduce((acc, item) => acc + Number(item.estimated_monthly_cost || 0), 0),
          lastDiscoverySyncAt: inventory
            .map((item) => item.last_discovery_sync_at)
            .filter(Boolean)
            .sort()
            .at(-1) || null,
        };

        setSummary(next);
      } catch (e) {
        if (!mounted) return;
        setError(e.message || "Failed to load platform dashboard");
      } finally {
        if (mounted) setLoading(false);
      }
    }

    load();
    return () => {
      mounted = false;
    };
  }, []);

  const cards = useMemo(
    () => [
      card("Connected Subscriptions", summary.connectedSubscriptionCount, "Authenticated Azure subscriptions"),
      card("Resource Groups", summary.resourceGroupCount, "Tracked in platform"),
      card("Resources", summary.resourceCount, "Catalogued architecture resources"),
      card("Monitoring Coverage", `${summary.liveResources}/${summary.monitoredResources}`, "Live resources over monitored resources"),
      card("Active Alerts", summary.activeAlerts, "Open + acknowledged + investigating"),
      card("Active Incidents", summary.activeIncidents, "Derived from active alerts"),
      card("Unused Resources", summary.unusedResources, `Estimated monthly waste: $${summary.monthlyWaste.toFixed(2)}`),
      card("HIPAA Score", summary.hipaaAverageScore === null ? "n/a" : summary.hipaaAverageScore, "Average from subscription-scoped assessments"),
      card("High Risk Subscriptions", summary.securityHighRiskCount, "Security summary risk level = high"),
      card("Estimated Monthly Cost", `$${summary.estimatedMonthlyTotal.toFixed(2)}`, "Subscription-scoped estimate totals"),
    ],
    [summary]
  );

  const azureNotConfigured = azureIntegration?.configuration_state !== "configured";

  return (
    <section className="workspace-panel">
      <div className="workspace-header">
        <div>
          <div className="workspace-eyebrow">Platform</div>
          <h1>Dashboard</h1>
          <p>Subscription-centric view across discovery, monitoring, cost, HIPAA, security, intelligence, and reports.</p>
        </div>
        <div className="toolbar-row">
          <button onClick={onOpenArchitectureStudio}>Open Architecture Studio</button>
          <button className="dismiss" onClick={onOpenSettings}>Open Settings</button>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      {loading && !azureIntegration && subscriptions.length === 0 ? (
        <div className="card"><p>Loading platform dashboard...</p></div>
      ) : azureNotConfigured ? (
        <section className="card">
          <div className="card-title"><h2>Azure Not Configured</h2></div>
          <div className="status-list">
            <div><strong>Configuration:</strong> {azureIntegration?.configuration_state || "not_configured"}</div>
            <div><strong>Connection:</strong> {azureIntegration?.connection_state || "not_configured"}</div>
            <div><strong>Message:</strong> {azureIntegration?.message || "Configure Azure credentials in Settings and run Test Azure Connection."}</div>
          </div>
          <div className="toolbar-row" style={{ marginTop: 10 }}>
            <button onClick={onOpenSettings}>Configure Azure</button>
          </div>
        </section>
      ) : (
        <>
          <div className="platform-grid">
            {cards.map((item) => (
              <article className="platform-card" key={item.title}>
                <h3>{item.title}</h3>
                <div className="platform-value">{item.value}</div>
                <p>{item.subtitle}</p>
              </article>
            ))}
          </div>

          <div className="platform-split">
            <section className="card">
              <div className="card-title"><h2>Connected Azure Subscriptions</h2><span>{subscriptions.length}</span></div>
              {subscriptions.length === 0 ? (
                <div className="empty">No subscriptions are linked yet. Add a subscription inside Architecture Studio and run discovery.</div>
              ) : (
                <div style={{ overflowX: "auto" }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Subscription ID</th>
                        <th>Tenant</th>
                        <th>Connection</th>
                        <th>RGs</th>
                        <th>Resources</th>
                        <th>Monitoring</th>
                        <th>Alerts</th>
                        <th>Incidents</th>
                        <th>Unused</th>
                        <th>HIPAA</th>
                        <th>Last Discovery</th>
                      </tr>
                    </thead>
                    <tbody>
                      {subscriptions.map((item) => (
                        <tr key={item.subscription_db_id}>
                          <td>
                            <strong>{item.subscription_name}</strong>
                            <div style={{ color: "#6f7d97", fontSize: 12 }}>{item.architecture_name}</div>
                          </td>
                          <td>{item.subscription_id || "n/a"}</td>
                          <td>{item.tenant_id || "n/a"}</td>
                          <td>{item.connection_state}</td>
                          <td>{item.resource_group_count}</td>
                          <td>{item.resource_count}</td>
                          <td>{item.monitoring_state} ({item.live_resource_count}/{item.monitored_resource_count})</td>
                          <td>{item.active_alert_count}</td>
                          <td>{item.active_incident_count}</td>
                          <td>{item.unused_resource_count} (${Number(item.estimated_monthly_waste || 0).toFixed(2)})</td>
                          <td>{item.hipaa_state}{item.hipaa_score === null ? "" : ` (${item.hipaa_score})`}</td>
                          <td>{item.last_discovery_sync_at || "never"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section className="card">
              <div className="card-title"><h2>Operational Context</h2></div>
              <div className="status-list">
                <div><strong>Azure connection:</strong> {azureIntegration?.connection_state || "unavailable"}</div>
                <div><strong>Authenticated subscription:</strong> {azureIntegration?.authenticated_subscription_name || "n/a"} ({azureIntegration?.authenticated_subscription_id || "n/a"})</div>
                <div><strong>Discovered resources:</strong> {azureIntegration?.discovered_resource_count ?? 0}</div>
                <div><strong>Discovered resource groups:</strong> {azureIntegration?.discovered_resource_group_count ?? 0}</div>
                <div><strong>Last successful discovery:</strong> {summary.lastDiscoverySyncAt || "never"}</div>
              </div>
            </section>
          </div>
        </>
      )}
    </section>
  );
}
