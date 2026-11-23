import { useState } from "react";
import { recordAssessmentRiskAcceptance } from "../services/api";
import { snapshotTime } from "./AzureSnapshotWorkspace";

export default function FindingRiskAcceptance({ assessmentId, finding, canManage, onRecord }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const decision = finding.risk_acceptance;
  const canRecord = canManage && finding.status !== "closed";

  async function record(event) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    setSaving(true);
    setError("");
    setFeedback("");
    try {
      const saved = await recordAssessmentRiskAcceptance(assessmentId, finding.id, {
        rationale: fields.get("rationale").trim(),
        expires_on: fields.get("expires_on"),
        previous_id: decision?.id || null,
      });
      onRecord(finding.id, saved);
      setFeedback("Risk acceptance recorded.");
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setSaving(false);
    }
  }

  if (!decision && !canRecord) return null;
  return <details>
    <summary>Risk acceptance{decision && (decision.active ? " - Active" : " - Expired")}</summary>
    {decision && <dl className="design-meta">
      <div><dt>Recorded by</dt><dd>{decision.actor_username}</dd></div>
      <div><dt>Recorded at</dt><dd>{snapshotTime(decision.created_at)}</dd></div>
      <div><dt>Expiry date (UTC)</dt><dd>{decision.expires_on}</dd></div>
      <div><dt>Rationale</dt><dd>{decision.rationale}</dd></div>
    </dl>}
    {canRecord && <form className="account-form" key={decision?.id} onSubmit={record}>
      <fieldset disabled={saving}>
        <label>Risk acceptance rationale<textarea name="rationale" rows={3} maxLength={2000} required /></label>
        <label>Risk acceptance expiry (UTC)<input name="expires_on" type="date" required /></label>
        <p>The acceptance expires at the start of this date in UTC. Use Update finding to record remediation and retest results.</p>
        <div><button type="submit">{saving ? "Recording..." : decision ? "Record replacement decision" : "Record risk acceptance"}</button></div>
      </fieldset>
    </form>}
    {error && <p className="error" role="alert">{error}</p>}
    {feedback && <p role="status">{feedback}</p>}
  </details>;
}
