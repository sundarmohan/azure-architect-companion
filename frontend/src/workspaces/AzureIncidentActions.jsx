import { useEffect, useRef, useState } from "react";
import { getAzureHealthIncidentActions, saveAzureHealthIncidentAction } from "../services/api";
import { displayLabel } from "./AzureSnapshotWorkspace";

function ActionForm({ subscription, incidentId, action, onSave }) {
  const draftId = useRef(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function save(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    setSaving(true);
    setError("");
    try {
      const id = action?.id || (draftId.current ??= crypto.randomUUID());
      const saved = await saveAzureHealthIncidentAction(subscription, incidentId, id, {
        kind: values.get("kind"),
        title: values.get("title").trim(),
        owner: values.get("owner").trim(),
        due_date: values.get("due_date"),
        status: values.get("status"),
        updated_at: action?.updated_at || null,
      });
      if (!action) {
        draftId.current = null;
        form.reset();
      }
      onSave(saved, Boolean(action));
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setSaving(false);
    }
  }

  return <form className="account-form" onSubmit={save}>
    <fieldset disabled={saving}>
      <label>Action type<select name="kind" defaultValue={action?.kind || "corrective"}>
        <option value="corrective">Corrective</option>
        <option value="preventive">Preventive</option>
      </select></label>
      <label>Action title<input name="title" maxLength={240} defaultValue={action?.title || ""} required /></label>
      <label>Action owner<input name="owner" maxLength={120} defaultValue={action?.owner || ""} required /></label>
      <label>Action due date<input name="due_date" type="date" defaultValue={action?.due_date || ""} required /></label>
      <label>Action status<select name="status" defaultValue={action?.status || "open"}>
        <option value="open">Open</option>
        <option value="in_progress">In progress</option>
        <option value="completed">Completed</option>
      </select></label>
      <div><button type="submit">{saving ? "Saving..." : action ? "Save action" : "Add action"}</button></div>
    </fieldset>
    {error && <p className="error" role="alert">{error}</p>}
  </form>;
}

export default function AzureIncidentActions({ subscription, incidentId, canEdit }) {
  const [actions, setActions] = useState(null);
  const [readCount, setReadCount] = useState(0);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");

  useEffect(() => {
    let active = true;
    getAzureHealthIncidentActions(subscription, incidentId).then((data) => {
      if (active) setActions(data);
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") setError(failure.message);
    });
    return () => { active = false; };
  }, [subscription, incidentId, readCount]);

  function reload() {
    setActions(null);
    setError("");
    setFeedback("");
    setReadCount((count) => count + 1);
  }

  function acceptSaved(saved, updated) {
    setActions((current) => {
      if (!current) return current;
      return current.some((action) => action.id === saved.id)
        ? current.map((action) => action.id === saved.id ? saved : action)
        : [...current, saved];
    });
    setFeedback(updated ? "Incident action updated." : "Incident action added.");
  }

  return <section className="account-form">
    <h3>Corrective and preventive actions</h3>
    <div><button type="button" className="dismiss" onClick={reload}>Reload incident actions</button></div>
    {error && <p className="error" role="alert">{error}</p>}
    {feedback && <p role="status">{feedback}</p>}
    {!actions && !error && <p role="status">Loading incident actions...</p>}
    {actions?.length > 0 ? <ul className="design-list">{actions.map((action) => (
      <li key={action.id}>
        <strong>{action.title}</strong>
        <dl className="design-meta">
          <div><dt>Type</dt><dd>{displayLabel(action.kind)}</dd></div>
          <div><dt>Status</dt><dd>{displayLabel(action.status)}</dd></div>
          <div><dt>Owner</dt><dd>{action.owner}</dd></div>
          <div><dt>Due date</dt><dd>{action.due_date}</dd></div>
        </dl>
        {canEdit && <details><summary>Edit {action.title}</summary>
          <ActionForm key={action.updated_at} subscription={subscription} incidentId={incidentId}
            action={action} onSave={acceptSaved} />
        </details>}
      </li>
    ))}</ul> : actions && <p>No incident actions recorded.</p>}
    {canEdit && actions && <details>
      <summary>New incident action</summary>
      <ActionForm subscription={subscription} incidentId={incidentId} onSave={acceptSaved} />
    </details>}
  </section>;
}
