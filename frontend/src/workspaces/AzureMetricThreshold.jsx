import { useEffect, useMemo, useState } from "react";
import { getAzureMetricThreshold, saveAzureMetricThreshold } from "../services/api";
import { displayLabel, snapshotTime } from "./AzureSnapshotWorkspace";

function choiceKey(choice) {
  return JSON.stringify([choice.resource_id, choice.metric, choice.aggregation]);
}

export default function AzureMetricThreshold({ subscription, canManage }) {
  const [workspace, setWorkspace] = useState(null);
  const [selectedKey, setSelectedKey] = useState("");
  const [direction, setDirection] = useState("above");
  const [limit, setLimit] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");

  useEffect(() => {
    let active = true;
    setWorkspace(null);
    setError("");
    getAzureMetricThreshold(subscription).then((data) => {
      if (!active) return;
      setWorkspace(data);
      if (data.threshold) {
        setSelectedKey(choiceKey(data.threshold));
        setDirection(data.threshold.direction);
        setLimit(String(data.threshold.limit));
      } else if (data.choices.length) {
        setSelectedKey(choiceKey(data.choices[0]));
      }
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") setError(failure.message);
    });
    return () => { active = false; };
  }, [subscription]);

  const selected = useMemo(() => workspace?.choices.find((choice) => choiceKey(choice) === selectedKey),
    [selectedKey, workspace]);

  async function save(event) {
    event.preventDefault();
    if (!selected) return;
    setBusy(true);
    setError("");
    setFeedback("");
    try {
      const saved = await saveAzureMetricThreshold(subscription, {
        resource_id: selected.resource_id,
        metric: selected.metric,
        aggregation: selected.aggregation,
        direction,
        limit: Number(limit),
      });
      setWorkspace(saved);
      setFeedback("Metric threshold saved.");
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  const assessment = workspace?.assessment;
  return <section className="card account-form">
    <h2>Metric threshold</h2>
    <p>Evaluate one saved Azure Monitor series for this subscription. This local advisory setting does not create an Azure alert rule.</p>
    {error && <p className="error" role="alert">{error}</p>}
    {feedback && <p role="status">{feedback}</p>}
    {!workspace && !error && <p role="status">Loading metric threshold…</p>}
    {workspace && workspace.choices.length === 0 && <p>Refresh Monitoring to collect a supported metric before configuring a threshold.</p>}
    {workspace && workspace.choices.length > 0 && <>
      {workspace.threshold && assessment && <dl className="design-meta">
        <div><dt>Evaluation</dt><dd>{displayLabel(assessment.status)}</dd></div>
        <div><dt>Latest value</dt><dd>{assessment.value ?? "Unavailable"}{workspace.threshold.unit ? ` ${workspace.threshold.unit}` : ""}</dd></div>
        <div><dt>Sample</dt><dd>{assessment.sample_at ? snapshotTime(assessment.sample_at) : "Unavailable"}</dd></div>
        <div><dt>Evidence freshness</dt><dd>{assessment.freshness ? displayLabel(assessment.freshness) : "Unavailable"}</dd></div>
      </dl>}
      {canManage ? <form onSubmit={save}>
        <fieldset disabled={busy}>
          <label>Saved metric<select value={selectedKey} required onChange={(event) => setSelectedKey(event.target.value)}>
            {workspace.choices.map((choice) => <option key={choiceKey(choice)} value={choiceKey(choice)}>
              {choice.resource_name} · {choice.metric} · {displayLabel(choice.aggregation)}
            </option>)}
          </select></label>
          <label>Condition<select value={direction} onChange={(event) => setDirection(event.target.value)}>
            <option value="above">Above</option><option value="below">Below</option>
          </select></label>
          <label>Limit{selected?.unit ? ` (${selected.unit})` : ""}<input type="number" step="any" required value={limit}
            onChange={(event) => setLimit(event.target.value)} /></label>
          <div><button type="submit">{busy ? "Saving…" : "Save threshold"}</button></div>
        </fieldset>
      </form> : !workspace.threshold && <p>A client administrator can configure this threshold.</p>}
    </>}
  </section>;
}
