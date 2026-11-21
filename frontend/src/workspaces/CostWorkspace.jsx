import { useEffect, useMemo, useState } from "react";
import {
  listArchitectures,
  listResources,
  estimateArchitectureCost,
  getArchitectureActualCost,
  listSubscriptions,
} from "../services/api";

export default function CostWorkspace() {
  const [architectures, setArchitectures] = useState([]);
  const [architectureId, setArchitectureId] = useState("");
  const [resources, setResources] = useState([]);
  const [subscriptions, setSubscriptions] = useState([]);
  const [region, setRegion] = useState("");
  const [serviceFilter, setServiceFilter] = useState("");
  const [skuFilter, setSkuFilter] = useState("");
  const [meterFilter, setMeterFilter] = useState("");
  const [currencyFilter, setCurrencyFilter] = useState("");
  const [quantityMin, setQuantityMin] = useState("");
  const [actualSubscription, setActualSubscription] = useState("");
  const [estimate, setEstimate] = useState(null);
  const [actual, setActual] = useState(null);
  const [termView, setTermView] = useState("monthly");
  const [loadingEstimate, setLoadingEstimate] = useState(false);
  const [loadingActual, setLoadingActual] = useState(false);
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
    async function loadMeta() {
      if (!architectureId) {
        setResources([]);
        setSubscriptions([]);
        return;
      }
      try {
        const [r, s] = await Promise.all([
          listResources(architectureId).catch(() => []),
          listSubscriptions(architectureId).catch(() => []),
        ]);
        setResources(r);
        setSubscriptions(s);
        setActualSubscription((prev) => prev || s.find((x) => x.subscription_id)?.subscription_id || "");
      } catch (e) {
        setError(e.message || "Failed to load cost metadata");
      }
    }
    loadMeta();
  }, [architectureId]);

  async function loadEstimatedCost() {
    if (!architectureId) return;
    setLoadingEstimate(true);
    setError("");
    try {
      const next = await estimateArchitectureCost(architectureId, region ? { region } : {});
      setEstimate(next);
    } catch (e) {
      setError(e.message || "Estimated cost request failed");
    } finally {
      setLoadingEstimate(false);
    }
  }

  async function loadActualCost() {
    if (!architectureId) return;
    setLoadingActual(true);
    setError("");
    try {
      const payload = actualSubscription ? { subscription_id: actualSubscription } : {};
      const next = await getArchitectureActualCost(architectureId, payload);
      setActual(next);
    } catch (e) {
      setError(e.message || "Actual cost request failed");
    } finally {
      setLoadingActual(false);
    }
  }

  const filterOptions = useMemo(() => {
    const items = estimate?.items || [];
    const services = Array.from(new Set(items.map((i) => i.resource_type).filter(Boolean))).sort();
    const skus = Array.from(new Set(items.map((i) => i.sku).filter(Boolean))).sort();
    const meters = Array.from(new Set(items.map((i) => i.meter_name).filter(Boolean))).sort();
    const currencies = Array.from(new Set(items.map((i) => i.currency).filter(Boolean))).sort();
    return { services, skus, meters, currencies };
  }, [estimate]);

  const filteredItems = useMemo(() => {
    const items = estimate?.items || [];
    return items.filter((item) => {
      if (serviceFilter && item.resource_type !== serviceFilter) return false;
      if (skuFilter && item.sku !== skuFilter) return false;
      if (meterFilter && item.meter_name !== meterFilter) return false;
      if (currencyFilter && item.currency !== currencyFilter) return false;
      if (quantityMin && Number(item.quantity || 0) < Number(quantityMin || 0)) return false;
      return true;
    });
  }, [estimate, serviceFilter, skuFilter, meterFilter, currencyFilter, quantityMin]);

  const displayedTotal = useMemo(() => {
    const key = termView === "annual" ? "annual_cost" : "monthly_cost";
    return filteredItems.reduce((acc, item) => acc + Number(item[key] || 0), 0);
  }, [filteredItems, termView]);

  return (
    <section className="workspace-panel">
      <div className="workspace-header">
        <div>
          <div className="workspace-eyebrow">FinOps</div>
          <h1>Cost / FinOps</h1>
          <p>Estimated and actual cost are separate first-class views backed by Azure Retail Prices and Azure Cost Management.</p>
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
          <input value={region} onChange={(e) => setRegion(e.target.value)} placeholder="Region (e.g., eastus)" />
          <button onClick={loadEstimatedCost} disabled={!architectureId || loadingEstimate}>{loadingEstimate ? "Loading..." : "Load Estimated Cost"}</button>
          <button onClick={loadActualCost} disabled={!architectureId || loadingActual}>{loadingActual ? "Loading..." : "Load Actual Cost"}</button>
        </div>

        <div className="toolbar-row">
          <select value={actualSubscription} onChange={(e) => setActualSubscription(e.target.value)}>
            <option value="">Auto subscription</option>
            {subscriptions.map((s) => (
              <option key={s.id} value={s.subscription_id || ""}>{s.name}{s.subscription_id ? ` (${s.subscription_id})` : ""}</option>
            ))}
          </select>
          <select value={termView} onChange={(e) => setTermView(e.target.value)}>
            <option value="monthly">Monthly view</option>
            <option value="annual">Annual view</option>
          </select>
        </div>

        <div className="platform-grid">
          <article className="platform-card">
            <h3>Architecture Resources</h3>
            <div className="platform-value" style={{ fontSize: 22 }}>{resources.length}</div>
            <p>Cost-relevant resources in selected architecture.</p>
          </article>
          <article className="platform-card">
            <h3>Estimated Pricing Source</h3>
            <div className="platform-value" style={{ fontSize: 22 }}>{estimate?.pricing_source || "not loaded"}</div>
            <p>Expected: azure_retail_prices with controlled fallback where needed.</p>
          </article>
          <article className="platform-card">
            <h3>Actual Pricing Source</h3>
            <div className="platform-value" style={{ fontSize: 22 }}>{actual?.pricing_source || "not loaded"}</div>
            <p>Expected: azure_cost_management.</p>
          </article>
        </div>

        {estimate && (
          <section className="card">
            <div className="card-title">
              <h2>Estimated Cost (Retail Pricing)</h2>
              <div className="actions">
                <button className="dismiss" onClick={() => setEstimate(null)}>Close</button>
              </div>
            </div>
            <div className="toolbar-row">
              <select value={serviceFilter} onChange={(e) => setServiceFilter(e.target.value)}>
                <option value="">All services/resource types</option>
                {filterOptions.services.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
              <select value={skuFilter} onChange={(e) => setSkuFilter(e.target.value)}>
                <option value="">All SKUs</option>
                {filterOptions.skus.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
              <select value={meterFilter} onChange={(e) => setMeterFilter(e.target.value)}>
                <option value="">All meters</option>
                {filterOptions.meters.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
              <select value={currencyFilter} onChange={(e) => setCurrencyFilter(e.target.value)}>
                <option value="">All currencies</option>
                {filterOptions.currencies.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
              <input value={quantityMin} onChange={(e) => setQuantityMin(e.target.value)} placeholder="Min quantity" />
            </div>
            <div className="status-list" style={{ marginTop: 10 }}>
              <div><strong>Filtered Total ({termView}):</strong> ${displayedTotal.toFixed(2)}</div>
              <div><strong>Region input:</strong> {region || "default"}</div>
              <div><strong>Rows:</strong> {filteredItems.length}</div>
            </div>
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Service</th>
                  <th>Region</th>
                  <th>SKU</th>
                  <th>Meter</th>
                  <th>Quantity</th>
                  <th>Unit</th>
                  <th>Currency</th>
                  <th>{termView === "annual" ? "Annual" : "Monthly"}</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.map((item) => (
                  <tr key={item.resource_id}>
                    <td>{item.name}</td>
                    <td>{item.resource_type}</td>
                    <td>{item.region}</td>
                    <td>{item.sku || "n/a"}</td>
                    <td>{item.meter_name || "n/a"}</td>
                    <td>{item.quantity}</td>
                    <td>{item.unit_of_measure || "n/a"}</td>
                    <td>{item.currency}</td>
                    <td>${Number(termView === "annual" ? item.annual_cost : item.monthly_cost).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        {actual && (
          <section className="card">
            <div className="card-title">
              <h2>Actual Cost (Billed Spend)</h2>
              <div className="actions">
                <button className="dismiss" onClick={() => setActual(null)}>Close</button>
              </div>
            </div>
            {!actual.available ? (
              <div className="pill warn">{actual.error || "Azure connection not configured for actual cost."}</div>
            ) : (
              <>
                <div className="status-list">
                  <div><strong>Total Cost:</strong> ${Number(actual.total_cost || 0).toFixed(2)} ({actual.currency || "USD"})</div>
                  <div><strong>Subscription:</strong> {actual.subscription_id || "n/a"}</div>
                  <div><strong>Date Range:</strong> {actual.start_date || "n/a"} to {actual.end_date || "n/a"}</div>
                </div>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Usage Date</th>
                      <th>Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(actual.daily || []).map((row, idx) => (
                      <tr key={`${row.usage_date}-${idx}`}>
                        <td>{row.usage_date}</td>
                        <td>${Number(row.cost || 0).toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </section>
        )}
      </section>
    </section>
  );
}
