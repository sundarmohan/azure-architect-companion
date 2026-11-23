import { useEffect, useState } from "react";
import { getAzureIncidentAttention } from "../services/api";
import { snapshotTime } from "./AzureSnapshotWorkspace";

export default function AzureIncidentAttention({ subscription, onSelect }) {
  const [attention, setAttention] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setAttention(null);
    setError("");
    getAzureIncidentAttention(subscription).then((data) => {
      if (active) setAttention(data);
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") setError(failure.message);
    });
    return () => { active = false; };
  }, [subscription]);

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!attention) return <p role="status">Loading incident attention…</p>;
  const { unassigned_incidents: unassigned, overdue_actions: overdue } = attention;
  return <section className="account-form">
    <h3>Needs attention</h3>
    {!unassigned.length && !overdue.length && <p>No unassigned open incidents or overdue actions.</p>}
    {unassigned.length > 0 && <>
      <p>{unassigned.length} open incident{unassigned.length === 1 ? " is" : "s are"} unassigned.</p>
      <ul className="design-list">{unassigned.map((incident) => <li key={incident.id}>
        <button type="button" className="dismiss" onClick={() => onSelect(incident)}>
          Review unassigned incident for {incident.resource_id}
        </button>
        <span> Created {snapshotTime(incident.created_at)}</span>
      </li>)}</ul>
    </>}
    {overdue.length > 0 && <>
      <p>{overdue.length} corrective or preventive action{overdue.length === 1 ? " is" : "s are"} overdue.</p>
      <ul className="design-list">{overdue.map(({ incident, action }) => <li key={`${incident.id}-${action.id}`}>
        <button type="button" className="dismiss" onClick={() => onSelect(incident)}>
          Review {action.title}
        </button>
        <span> Due {action.due_date} · {action.owner}</span>
      </li>)}</ul>
    </>}
  </section>;
}
