import { useEffect, useState } from "react";
import { getAzureActualCost, getAzureConnectionStatus } from "../services/api";
import { snapshotTime } from "./AzureSnapshotWorkspace";

const utcDate = (date) => date.toISOString().slice(0, 10);

function SubscriptionCosts({ subscription }) {
  const today = new Date();
  const monthStart = utcDate(new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), 1)));
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function query(event) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const start = fields.get("start");
    const end = fields.get("end");
    setError("");
    setResult(null);
    if (end < start || Date.parse(end) - Date.parse(start) >= 31 * 86400000) {
      setError("Choose a date range of at most 31 days.");
      return;
    }
    setLoading(true);
    try {
      setResult(await getAzureActualCost(subscription, start, end));
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setLoading(false);
    }
  }

  const money = result?.available
    ? new Intl.NumberFormat(undefined, { style: "currency", currency: result.currency })
    : null;

  return <>
    <form className="account-form" onSubmit={query}>
      <fieldset disabled={loading}>
        <label>Start date (UTC)<input name="start" type="date" defaultValue={monthStart} max={utcDate(today)} required /></label>
        <label>End date (UTC)<input name="end" type="date" defaultValue={utcDate(today)} max={utcDate(today)} required /></label>
        <button type="submit">{loading ? "Loading charges…" : "Load actual cost"}</button>
      </fieldset>
    </form>
    {error && <p className="error" role="alert">{error}</p>}
    {result && !result.available && <p role="status">{result.error || "Actual cost unavailable."}</p>}
    {money && <>
      <p>Total actual cost <strong>{money.format(result.total_cost)}</strong></p>
      <p>Azure Cost Management · {result.start_date} to {result.end_date} UTC · Retrieved {snapshotTime(result.retrieved_at)}</p>
      <div className="design-table"><table className="table" aria-label="Daily actual Azure cost">
        <thead><tr><th scope="col">Usage date (UTC)</th><th scope="col">Actual cost</th></tr></thead>
        <tbody>{result.daily.map((day) => <tr key={day.usage_date}>
          <td>{day.usage_date}</td><td>{money.format(day.cost)}</td>
        </tr>)}</tbody>
      </table></div>
    </>}
  </>;
}

export default function AzureActualCostWorkspace() {
  const [subscriptions, setSubscriptions] = useState(null);
  const [selection, setSelection] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    getAzureConnectionStatus().then((connection) => {
      if (!active) return;
      const ids = connection.configured_subscription_ids?.length ? connection.configured_subscription_ids
        : [connection.configured_subscription_id].filter(Boolean);
      setSubscriptions(ids);
      setSelection(ids[0] || "");
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") setError(failure.message);
    });
    return () => { active = false; };
  }, []);

  return <section className="workspace-panel">
    <h1>Actual Azure cost</h1>
    <div className="card account-form">
      <p>Review reported daily charges for a configured subscription. Billing updates can arrive after usage.</p>
      {error ? <p className="error" role="alert">{error}</p>
        : !subscriptions ? <p role="status">Loading Azure subscriptions…</p>
        : !subscriptions.length ? <p>Configure an Azure connection to view actual cost.</p>
        : <>
          <label>Subscription<select value={selection} onChange={(event) => setSelection(event.target.value)}>
            {subscriptions.map((id) => <option key={id} value={id}>{id}</option>)}
          </select></label>
          <SubscriptionCosts key={selection} subscription={selection} />
        </>}
    </div>
  </section>;
}
