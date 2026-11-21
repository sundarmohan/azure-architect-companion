import { useEffect, useState } from "react";
import { clearAzureCredentials, getAzureConnectionStatus, saveAzureCredentials, testAzureIntegration } from "../services/api";

const CONNECTION_STATE = {
  configured: "Credentials are saved.",
  not_configured: "No credentials are saved.",
  authentication_failure: "Azure authentication failed.",
  permission_failure: "The service principal cannot read this subscription.",
  provider_error: "The Azure subscription could not be read.",
};

export default function AzureConnectionWorkspace({ canManage }) {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [tested, setTested] = useState(false);
  const [testSubscription, setTestSubscription] = useState("");
  const subscriptions = status?.configured_subscription_ids
    || (status?.configured_subscription_id ? [status.configured_subscription_id] : []);

  useEffect(() => {
    getAzureConnectionStatus().then(setStatus).catch((failure) => {
      if (failure.name !== "AbortError") setError(failure.message);
    });
  }, []);

  async function update(action, isTest = false) {
    setBusy(true);
    setError("");
    setTested(false);
    try {
      const next = (await action()) ?? await getAzureConnectionStatus();
      setStatus(next);
      if (!isTest) setTestSubscription("");
      setTested(isTest);
      return true;
    } catch (failure) {
      setError(failure.message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function save(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    values.tenant_id = values.tenant_id.trim();
    values.client_id = values.client_id.trim();
    values.subscription_id = values.subscription_id.trim();
    values.additional_subscription_ids = values.additional_subscription_ids.split(/[\s,]+/).filter(Boolean);
    if (await update(() => saveAzureCredentials(values))) form.reset();
  }

  return <section className="workspace-panel">
    <h1>Azure Connection</h1>
    <p>Connect a read-only service principal for the active client.</p>
    {error && <div className="error" role="alert">{error}</div>}
    <div className="card account-form">
      <h2>Connection status</h2>
      <p role="status">{tested && status?.connection_state === "configured"
        ? "Connection passed. Azure returned the subscription."
        : status?.message || CONNECTION_STATE[status?.connection_state] || (!error && "Loading…")}</p>
      {subscriptions.length > 0 && <p>Configured subscriptions {subscriptions.join(", ")}</p>}
      {canManage && subscriptions.length > 1 && <label>Subscription to test<select value={testSubscription || subscriptions[0]} disabled={busy}
        onChange={(event) => {
          setTestSubscription(event.target.value);
          setTested(false);
        }}>
        {subscriptions.map((id) => <option key={id} value={id}>{id}</option>)}
      </select></label>}
      {canManage && <div className="actions">
        <button onClick={() => update(() => testAzureIntegration(testSubscription || subscriptions[0]), true)} disabled={busy || !subscriptions.length}>Test connection</button>
        <button onClick={() => {
          if (window.confirm("Clear this client's Azure connection?")) void update(clearAzureCredentials);
        }} disabled={busy}>Clear credentials</button>
      </div>}
    </div>
    {canManage && <form className="card account-form" onSubmit={save} autoComplete="off">
      <h2>Save credentials</h2>
      <fieldset disabled={busy}>
        <label>Microsoft Entra tenant ID<input name="tenant_id" required /></label>
        <label>Application client ID<input name="client_id" required /></label>
        <label>Client secret<input name="client_secret" type="password" autoComplete="new-password" required /></label>
        <label>Primary subscription ID<input name="subscription_id" required /></label>
        <label>Additional subscription IDs<textarea name="additional_subscription_ids" rows={3} placeholder="One subscription ID per line" /></label>
        <button type="submit">Save credentials</button>
      </fieldset>
    </form>}
  </section>;
}
