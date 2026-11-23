import { useEffect, useRef, useState } from "react";
import { getAzureRestoreTests, recordAzureRestoreTest } from "../services/api";
import { displayLabel, snapshotTime } from "./AzureSnapshotWorkspace";

export default function AzureRestoreTests({ subscription, canEdit }) {
  const [records, setRecords] = useState(null);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [saving, setSaving] = useState(false);
  const draftId = useRef(null);

  useEffect(() => {
    let active = true;
    setRecords(null);
    setError("");
    getAzureRestoreTests(subscription).then((data) => {
      if (active) setRecords(data);
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") setError(failure.message);
    });
    return () => { active = false; };
  }, [subscription]);

  async function save(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    setSaving(true);
    setError("");
    setFeedback("");
    try {
      const id = draftId.current ??= crypto.randomUUID();
      const duration = values.get("recovery_minutes");
      const saved = await recordAzureRestoreTest(subscription, id, {
        resource_name: values.get("resource_name").trim(),
        tested_at: new Date(values.get("tested_at")).toISOString(),
        outcome: values.get("outcome"),
        recovery_minutes: duration ? Number(duration) : null,
        evidence_reference: values.get("evidence_reference").trim() || null,
        notes: values.get("notes").trim() || null,
      });
      setRecords((current) => [saved, ...(current || [])].slice(0, 50));
      draftId.current = null;
      form.reset();
      setFeedback("Restore test evidence recorded.");
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setSaving(false);
    }
  }

  return <section className="card account-form">
    <h3>Restore test evidence</h3>
    <p>Record a completed, human-validated restore exercise. References should identify approved evidence without including credentials or sensitive recovered data.</p>
    {error && <p className="error" role="alert">{error}</p>}
    {feedback && <p role="status">{feedback}</p>}
    {!records && !error && <p role="status">Loading restore tests…</p>}
    {records?.length > 0 ? <ul className="design-list">{records.map((record) => <li key={record.id}>
      <strong>{record.resource_name} · {displayLabel(record.outcome)}</strong>
      <dl className="design-meta">
        <div><dt>Tested</dt><dd>{snapshotTime(record.tested_at)}</dd></div>
        <div><dt>Observed recovery time</dt><dd>{record.recovery_minutes ? `${record.recovery_minutes} minutes` : "Not recorded"}</dd></div>
        <div><dt>Evidence reference</dt><dd>{record.evidence_reference || "Not recorded"}</dd></div>
        {record.notes && <div><dt>Notes</dt><dd>{record.notes}</dd></div>}
      </dl>
    </li>)}</ul> : records && <p>No restore tests are recorded for this subscription.</p>}
    {canEdit && records && <details>
      <summary>Record restore test</summary>
      <form className="account-form" onSubmit={save}>
        <fieldset disabled={saving}>
          <label>Restored resource or workload<input name="resource_name" maxLength={200} required /></label>
          <label>Test completed at<input name="tested_at" type="datetime-local" required /></label>
          <label>Outcome<select name="outcome" defaultValue="passed">
            <option value="passed">Passed</option><option value="partial">Partial</option><option value="failed">Failed</option>
          </select></label>
          <label>Observed recovery time (minutes)<input name="recovery_minutes" type="number" min="1" max="525600" step="1" /></label>
          <label>Evidence reference<input name="evidence_reference" maxLength={500} /></label>
          <label>Notes<textarea name="notes" maxLength={1000} rows={3} /></label>
          <div><button type="submit">{saving ? "Saving…" : "Record restore test"}</button></div>
        </fieldset>
      </form>
    </details>}
  </section>;
}
