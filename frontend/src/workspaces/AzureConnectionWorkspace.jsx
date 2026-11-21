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
      setStatus((await action()) ?? await getAzureConnectionStatus());
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
      {status?.configured_subscription_id && <p>Subscription {status.configured_subscription_id}</p>}
      {canManage && <div className="actions">
        <button onClick={() => update(testAzureIntegration, true)} disabled={busy}>Test connection</button>
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
        <label>Subscription ID<input name="subscription_id" required /></label>
        <button type="submit">Save credentials</button>
      </fieldset>
    </form>}
  </section>;
}
