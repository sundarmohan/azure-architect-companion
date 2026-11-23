import { useEffect, useState } from "react";
import { getAzureActualCost, getAzureConnectionStatus, getAzureCostBudget, getAzureCostRecommendations,
  saveAzureCostBudget } from "../services/api";
import { displayLabel, snapshotTime } from "./AzureSnapshotWorkspace";

const utcDate = (date) => date.toISOString().slice(0, 10);
const DAY_MS = 86400000;
const BASELINE_DAYS = 7;
const MIN_INCREASE = 0.5;
const MIN_CURRENCY_INCREASE = 1;

function coversMonthlyBudget(result, today) {
  const start = new Date(result.start_date);
  if (start.getUTCDate() !== 1) return false;
  start.setUTCMonth(start.getUTCMonth() + 1, 0);
  const monthEnd = utcDate(start);
  return result.end_date === (monthEnd < today ? monthEnd : today);
}

function reviewDailyCharges(result, today) {
  const costs = new Map(result.daily.map(({ usage_date, cost }) => [usage_date, cost]));
  const previous = [];
  const anomalies = [];
  let reviewed = 0;
  let missing = 0;
  const reviewEnd = Math.min(Date.parse(result.end_date), Date.parse(today) - DAY_MS);
  for (let time = Date.parse(result.start_date); time <= reviewEnd; time += DAY_MS) {
    const date = utcDate(new Date(time));
    const cost = costs.get(date);
    if (!Number.isFinite(cost)) {
      missing++;
      previous.length = 0;
      continue;
    }
    if (previous.length === BASELINE_DAYS) {
      const sorted = [...previous].sort((left, right) => left - right);
      const median = sorted[Math.floor(BASELINE_DAYS / 2)];
      if (median > 0) {
        reviewed++;
        if (cost >= median * (1 + MIN_INCREASE) && cost - median >= MIN_CURRENCY_INCREASE) {
          anomalies.push({ date, cost, median });
        }
      }
      previous.shift();
    }
    previous.push(cost);
  }
  return { anomalies, reviewed, missing };
}

function CostAnomalyReview({ result, today, money }) {
  const { anomalies, reviewed, missing } = reviewDailyCharges(result, today);
  const percent = new Intl.NumberFormat(undefined, { style: "percent", maximumFractionDigits: 1 });
  return <section className="account-form">
    <h2>Cost anomaly review</h2>
    <p>For completed UTC days with seven consecutive prior charges and a positive median, flag charges at least
      50% and {money.format(MIN_CURRENCY_INCREASE)} above that median. Missing charges reset the baseline.</p>
    {missing > 0 && <p>Missing charge dates in the selected range: {missing}.</p>}
    {reviewed === 0
      ? <p>Daily evidence is insufficient for anomaly comparison.</p>
      : <p>Compared {reviewed} {reviewed === 1 ? "day" : "days"}. {anomalies.length
        ? "Review the flagged increases." : "No increases met the review threshold."}</p>}
    {anomalies.length > 0 && <div className="design-table">
      <table className="table" aria-label="Cost increases for review">
        <thead><tr><th scope="col">Usage date (UTC)</th><th scope="col">Actual cost</th>
          <th scope="col">Prior seven-day median</th><th scope="col">Increase</th></tr></thead>
        <tbody>{anomalies.map(({ date, cost, median }) => <tr key={date}>
          <td>{date}</td><td>{money.format(cost)}</td><td>{money.format(median)}</td>
          <td>{percent.format((cost - median) / median)}</td>
        </tr>)}</tbody>
      </table>
    </div>}
  </section>;
}

function SubscriptionBudget({ subscription, canEdit, result, today }) {
  const [budget, setBudget] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const currency = (result?.available && result.currency) || budget?.currency;
  const money = budget ? new Intl.NumberFormat(undefined, { style: "currency", currency: budget.currency }) : null;

  useEffect(() => {
    let active = true;
    getAzureCostBudget(subscription).then((data) => {
      if (active) setBudget(data);
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") setError(failure.message);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [subscription]);

  async function save(event) {
    event.preventDefault();
    const amount = new FormData(event.currentTarget).get("amount");
    setError("");
    setFeedback("");
    setSaving(true);
    try {
      setBudget(await saveAzureCostBudget(subscription, { amount, currency }));
      setFeedback("Monthly budget saved.");
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setSaving(false);
    }
  }

  return <section className="account-form">
    <h2>Monthly budget</h2>
    <p>This threshold is stored in MonitorAI.</p>
    {loading && <p role="status">Loading monthly budget…</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {!loading && !error && !budget && <p>No monthly budget is configured.</p>}
    {budget && <p>Current monthly budget <strong>{money.format(budget.amount)}</strong> ({budget.currency})</p>}
    {budget && result?.available && (result.currency !== budget.currency
      ? <p>Budget comparison unavailable because the charge and budget currencies differ.</p>
      : !coversMonthlyBudget(result, today) ? <p>Load a complete month or this month to date for comparison.</p>
        : <p>Reported charges use {new Intl.NumberFormat(undefined, { style: "percent", maximumFractionDigits: 1 })
          .format(result.total_cost / Number(budget.amount))} of the current budget.</p>)}
    {!loading && canEdit && (currency
      ? <form className="account-form" onSubmit={save} key={`${currency}-${budget?.amount || ""}`}>
        <fieldset disabled={saving}>
          <label>Monthly budget amount ({currency})<input name="amount" type="number" min="0.01" max="999999999999.99"
            step="0.01" defaultValue={budget?.currency === currency ? budget.amount : ""} required /></label>
          <button type="submit">{saving ? "Saving…" : "Save monthly budget"}</button>
        </fieldset>
      </form>
      : <p>Load Azure charges to identify the billing currency before setting a budget.</p>)}
    {feedback && <p role="status">{feedback}</p>}
  </section>;
}

const ADVISOR_UNAVAILABLE = {
  authentication_failure: "Azure Advisor authentication failed.",
  permission_failure: "The Azure connection lacks permission to read Advisor recommendations.",
  unsupported: "Azure Advisor recommendations are unavailable for this subscription.",
  provider_error: "Azure Advisor did not return usable recommendation evidence.",
};

function AdvisorCostRecommendations({ subscription }) {
  const [snapshot, setSnapshot] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setSnapshot(null);
    setError("");
    try {
      setSnapshot(await getAzureCostRecommendations(subscription));
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setLoading(false);
    }
  }

  return <section className="account-form">
    <h2>Azure Advisor cost recommendations</h2>
    <button type="button" disabled={loading} onClick={load}>{loading ? "Loading recommendations…" : "Load cost recommendations"}</button>
    {error && <p className="error" role="alert">{error}</p>}
    {snapshot && <>
      {snapshot.retrieved_at && <p>Retrieved {snapshotTime(snapshot.retrieved_at)}</p>}
      {ADVISOR_UNAVAILABLE[snapshot.status] && <p role="status">{ADVISOR_UNAVAILABLE[snapshot.status]}</p>}
      {snapshot.status === "partial_failure" && <p>Some Advisor entries could not be verified for this subscription.</p>}
      {snapshot.truncated && <p>Recommendation coverage is limited to the first Azure response page, up to 25 entries.</p>}
      {snapshot.status === "synced" && !snapshot.recommendations.length && <p>{snapshot.truncated
        ? "The bounded Azure response contained no displayable cost recommendations."
        : "Azure Advisor returned no cost recommendations."}</p>}
      {snapshot.recommendations.length > 0 && <ul className="design-list">
        {snapshot.recommendations.map((item) => <li key={item.id}>
          <strong>{item.recommendation}</strong>
          {item.problem && <p>{item.problem}</p>}
          {item.resource_id && <p>{item.resource_id}</p>}
          {item.impact && <p>Advisor impact {displayLabel(item.impact)}</p>}
          {item.last_updated && <p>Advisor updated {snapshotTime(item.last_updated)}</p>}
        </li>)}
      </ul>}
    </>}
  </section>;
}

function SubscriptionCosts({ subscription, canEdit }) {
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
    if (end < start || Date.parse(end) - Date.parse(start) >= 31 * DAY_MS) {
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
      <CostAnomalyReview result={result} today={utcDate(today)} money={money} />
    </>}
    <SubscriptionBudget subscription={subscription} canEdit={canEdit} result={result} today={utcDate(today)} />
    <AdvisorCostRecommendations subscription={subscription} />
  </>;
}

export default function AzureActualCostWorkspace({ canEdit = false }) {
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
          <SubscriptionCosts key={selection} subscription={selection} canEdit={canEdit} />
        </>}
    </div>
  </section>;
}
