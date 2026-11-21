import { useEffect, useMemo, useState } from "react";
import {
  clearCloudAccountCredentials,
  clearAzureCredentials,
  clearProviderApiKey,
  getSettingsOverview,
  saveCloudAccountCredentials,
  saveAzureCredentials,
  testCloudAccountConnection,
  testAzureIntegration,
  testProviderConnection,
  updateProviderApiKey,
} from "../services/api";

const PROVIDERS = [
  { id: "openai", label: "OpenAI" },
  { id: "gemini", label: "Gemini" },
];

const CLOUD_ACCOUNT_PROVIDERS = [
  { id: "aws", label: "AWS" },
  { id: "gcp", label: "GCP" },
];

export default function SettingsWorkspace() {
  const [overview, setOverview] = useState(null);
  const [keys, setKeys] = useState({ openai: "", gemini: "" });
  const [azure, setAzure] = useState({
    tenant_id: "",
    client_id: "",
    client_secret: "",
    subscription_id: "",
  });
  const [cloudAccounts, setCloudAccounts] = useState({
    aws: {
      access_key_id: "",
      secret_access_key: "",
      region: "",
    },
    gcp: {
      service_account_json: "",
    },
  });
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState({
    openaiSave: false,
    geminiSave: false,
    openaiTest: false,
    geminiTest: false,
    openaiClear: false,
    geminiClear: false,
    azureSave: false,
    azureClear: false,
    azureTest: false,
    awsSave: false,
    awsClear: false,
    awsTest: false,
    gcpSave: false,
    gcpClear: false,
    gcpTest: false,
  });
  const [error, setError] = useState("");
  const [azureActionResult, setAzureActionResult] = useState({
    type: "",
    text: "",
  });
  const [cloudActionResults, setCloudActionResults] = useState({
    aws: { type: "", text: "" },
    gcp: { type: "", text: "" },
  });

  const providerMap = useMemo(() => {
    const map = {};
    const providers = overview?.ai_providers || [];
    providers.forEach((item) => {
      map[item.provider] = item;
    });
    return map;
  }, [overview]);

  const cloudAccountMap = useMemo(() => {
    const map = {};
    const providers = overview?.cloud_accounts || [];
    providers.forEach((item) => {
      map[item.provider] = item;
    });
    return map;
  }, [overview]);

  async function loadSettings() {
    setLoading(true);
    setError("");
    try {
      const next = await getSettingsOverview();
      setOverview(next);
    } catch (e) {
      setError(e.message || "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSettings();
  }, []);

  function setBusyState(name, next) {
    setBusy((prev) => ({ ...prev, [name]: next }));
  }

  async function saveKey(provider) {
    const value = (keys[provider] || "").trim();
    if (!value) return;
    setBusyState(`${provider}Save`, true);
    setError("");
    try {
      await updateProviderApiKey(provider, { api_key: value });
      setKeys((prev) => ({ ...prev, [provider]: "" }));
      await loadSettings();
    } catch (e) {
      setError(e.message || "Failed to save provider key");
    } finally {
      setBusyState(`${provider}Save`, false);
    }
  }

  async function clearKey(provider) {
    setBusyState(`${provider}Clear`, true);
    setError("");
    try {
      await clearProviderApiKey(provider);
      await loadSettings();
    } catch (e) {
      setError(e.message || "Failed to clear provider key");
    } finally {
      setBusyState(`${provider}Clear`, false);
    }
  }

  async function testProvider(provider) {
    setBusyState(`${provider}Test`, true);
    setError("");
    try {
      await testProviderConnection(provider);
      await loadSettings();
    } catch (e) {
      setError(e.message || "Provider test failed");
    } finally {
      setBusyState(`${provider}Test`, false);
    }
  }

  async function runAzureTest() {
    setBusyState("azureTest", true);
    setError("");
    setAzureActionResult({ type: "", text: "" });
    try {
      const result = await testAzureIntegration();
      await loadSettings();
      const state = result?.connection_state || "unknown";
      const message = result?.message || "Azure test completed.";
      const success = state === "configured";
      setAzureActionResult({
        type: success ? "success" : "warn",
        text: `Test result: ${success ? "passed" : "failed"} (${state}). ${message}`,
      });
    } catch (e) {
      const message = e.message || "Azure test failed";
      setError(message);
      setAzureActionResult({
        type: "error",
        text: `Test result: failed. ${message}`,
      });
    } finally {
      setBusyState("azureTest", false);
    }
  }

  async function saveAzure() {
    const payload = {
      tenant_id: (azure.tenant_id || "").trim(),
      client_id: (azure.client_id || "").trim(),
      client_secret: (azure.client_secret || "").trim(),
      subscription_id: (azure.subscription_id || "").trim(),
    };

    setBusyState("azureSave", true);
    setError("");
    setAzureActionResult({ type: "", text: "" });
    try {
      const result = await saveAzureCredentials(payload);
      setAzure((prev) => ({ ...prev, client_secret: "" }));
      await loadSettings();
      const state = result?.connection_state || "unavailable";
      const message = result?.message || "Azure credentials saved.";
      setAzureActionResult({
        type: "success",
        text: `Save result: completed (${state}). ${message}`,
      });
    } catch (e) {
      const message = e.message || "Failed to save Azure credentials";
      setError(message);
      setAzureActionResult({
        type: "error",
        text: `Save result: failed. ${message}`,
      });
    } finally {
      setBusyState("azureSave", false);
    }
  }

  async function clearAzure() {
    setBusyState("azureClear", true);
    setError("");
    setAzureActionResult({ type: "", text: "" });
    try {
      const result = await clearAzureCredentials();
      setAzure({ tenant_id: "", client_id: "", client_secret: "", subscription_id: "" });
      await loadSettings();
      const message = result?.message || "Azure credentials cleared.";
      setAzureActionResult({
        type: "success",
        text: `Clear result: completed. ${message}`,
      });
    } catch (e) {
      const message = e.message || "Failed to clear Azure credentials";
      setError(message);
      setAzureActionResult({
        type: "error",
        text: `Clear result: failed. ${message}`,
      });
    } finally {
      setBusyState("azureClear", false);
    }
  }

  function setCloudAccountValue(provider, key, value) {
    setCloudAccounts((prev) => ({
      ...prev,
      [provider]: {
        ...(prev[provider] || {}),
        [key]: value,
      },
    }));
  }

  async function saveCloudAccount(provider) {
    setBusyState(`${provider}Save`, true);
    setError("");
    setCloudActionResults((prev) => ({ ...prev, [provider]: { type: "", text: "" } }));
    try {
      const payload = cloudAccounts[provider] || {};
      const result = await saveCloudAccountCredentials(provider, payload);
      if (provider === "aws") {
        setCloudAccounts((prev) => ({
          ...prev,
          aws: {
            ...prev.aws,
            secret_access_key: "",
          },
        }));
      }
      if (provider === "gcp") {
        setCloudAccounts((prev) => ({
          ...prev,
          gcp: {
            service_account_json: "",
          },
        }));
      }
      await loadSettings();
      setCloudActionResults((prev) => ({
        ...prev,
        [provider]: {
          type: "success",
          text: `Save result: completed (${result?.connection_state || "unavailable"}). ${result?.message || "Cloud account credentials saved."}`,
        },
      }));
    } catch (e) {
      const message = e.message || "Failed to save cloud account credentials";
      setError(message);
      setCloudActionResults((prev) => ({
        ...prev,
        [provider]: {
          type: "error",
          text: `Save result: failed. ${message}`,
        },
      }));
    } finally {
      setBusyState(`${provider}Save`, false);
    }
  }

  async function clearCloudAccount(provider) {
    setBusyState(`${provider}Clear`, true);
    setError("");
    setCloudActionResults((prev) => ({ ...prev, [provider]: { type: "", text: "" } }));
    try {
      const result = await clearCloudAccountCredentials(provider);
      if (provider === "aws") {
        setCloudAccounts((prev) => ({
          ...prev,
          aws: {
            access_key_id: "",
            secret_access_key: "",
            region: "",
          },
        }));
      }
      if (provider === "gcp") {
        setCloudAccounts((prev) => ({
          ...prev,
          gcp: {
            service_account_json: "",
          },
        }));
      }
      await loadSettings();
      setCloudActionResults((prev) => ({
        ...prev,
        [provider]: {
          type: "success",
          text: `Clear result: completed. ${result?.message || "Cloud account credentials cleared."}`,
        },
      }));
    } catch (e) {
      const message = e.message || "Failed to clear cloud account credentials";
      setError(message);
      setCloudActionResults((prev) => ({
        ...prev,
        [provider]: {
          type: "error",
          text: `Clear result: failed. ${message}`,
        },
      }));
    } finally {
      setBusyState(`${provider}Clear`, false);
    }
  }

  async function testCloudAccount(provider) {
    setBusyState(`${provider}Test`, true);
    setError("");
    setCloudActionResults((prev) => ({ ...prev, [provider]: { type: "", text: "" } }));
    try {
      const result = await testCloudAccountConnection(provider);
      await loadSettings();
      const state = result?.connection_state || "unknown";
      const success = state === "configured";
      setCloudActionResults((prev) => ({
        ...prev,
        [provider]: {
          type: success ? "success" : "warn",
          text: `Test result: ${success ? "passed" : "failed"} (${state}). ${result?.message || "Connection test completed."}`,
        },
      }));
    } catch (e) {
      const message = e.message || "Cloud account test failed";
      setError(message);
      setCloudActionResults((prev) => ({
        ...prev,
        [provider]: {
          type: "error",
          text: `Test result: failed. ${message}`,
        },
      }));
    } finally {
      setBusyState(`${provider}Test`, false);
    }
  }

  return (
    <section className="workspace-panel">
      <div className="workspace-header">
        <div>
          <div className="workspace-eyebrow">Integrations</div>
          <h1>Settings</h1>
          <p>Provider key management and integration status for future AI and Azure wiring.</p>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      <section className="card workspace-stack">
        <div className="toolbar-row">
          <button className="dismiss" onClick={loadSettings} disabled={loading}>{loading ? "Loading..." : "Refresh Settings"}</button>
        </div>

        <section className="card">
          <div className="card-title"><h2>AI Providers</h2></div>
          <div className="workspace-stack">
            {PROVIDERS.map((provider) => {
              const state = providerMap[provider.id] || {
                provider: provider.id,
                enabled: false,
                configuration_state: "not_configured",
                connection_state: "unavailable",
                message: "No status available yet.",
              };
              return (
                <section key={provider.id} className="card">
                  <div className="card-title"><h3>{provider.label}</h3></div>
                  <div className="status-list">
                    <div><strong>Enabled:</strong> {state.enabled ? "yes" : "no"}</div>
                    <div><strong>Configuration:</strong> {state.configuration_state}</div>
                    <div><strong>Connection:</strong> {state.connection_state}</div>
                    {state.message ? <div><strong>Message:</strong> {state.message}</div> : null}
                  </div>
                  <div className="toolbar-row" style={{ marginTop: 10 }}>
                    <input
                      type="password"
                      autoComplete="off"
                      value={keys[provider.id]}
                      onChange={(e) => setKeys((prev) => ({ ...prev, [provider.id]: e.target.value }))}
                      placeholder={`Enter ${provider.label} API key`}
                    />
                    <button onClick={() => saveKey(provider.id)} disabled={busy[`${provider.id}Save`] || !keys[provider.id].trim()}>
                      {busy[`${provider.id}Save`] ? "Saving..." : "Save Key"}
                    </button>
                    <button className="dismiss" onClick={() => testProvider(provider.id)} disabled={busy[`${provider.id}Test`]}>
                      {busy[`${provider.id}Test`] ? "Testing..." : "Test Connection"}
                    </button>
                    <button className="danger" onClick={() => clearKey(provider.id)} disabled={busy[`${provider.id}Clear`]}>
                      {busy[`${provider.id}Clear`] ? "Clearing..." : "Clear Key"}
                    </button>
                  </div>
                  <div className="pill" style={{ marginTop: 10 }}>Saved keys are never returned to the UI.</div>
                </section>
              );
            })}
          </div>
        </section>

        <section className="card">
          <div className="card-title"><h2>Azure Integration</h2></div>
          <div className="status-list">
            <div><strong>Enabled:</strong> {overview?.azure_integration?.enabled ? "yes" : "no"}</div>
            <div><strong>Configuration:</strong> {overview?.azure_integration?.configuration_state || "not_configured"}</div>
            <div><strong>Connection:</strong> {overview?.azure_integration?.connection_state || "unavailable"}</div>
            <div><strong>Configured tenant:</strong> {overview?.azure_integration?.configured_tenant_id || "n/a"}</div>
            <div><strong>Configured subscription:</strong> {overview?.azure_integration?.configured_subscription_id || "n/a"}</div>
            <div><strong>Configured client:</strong> {overview?.azure_integration?.configured_client_id_hint || "n/a"}</div>
            <div><strong>Authenticated tenant:</strong> {overview?.azure_integration?.authenticated_tenant_id || "n/a"}</div>
            <div><strong>Authenticated subscription:</strong> {overview?.azure_integration?.authenticated_subscription_id || "n/a"}</div>
            <div><strong>Authenticated subscription name:</strong> {overview?.azure_integration?.authenticated_subscription_name || "n/a"}</div>
            <div><strong>Authenticated subscription state:</strong> {overview?.azure_integration?.authenticated_subscription_state || "n/a"}</div>
            <div><strong>Discovered resource groups:</strong> {overview?.azure_integration?.discovered_resource_group_count ?? 0}</div>
            <div><strong>Discovered resources:</strong> {overview?.azure_integration?.discovered_resource_count ?? 0}</div>
            <div><strong>Last discovery sync:</strong> {overview?.azure_integration?.last_discovery_sync_at || "never"}</div>
            <div><strong>Last tested:</strong> {overview?.azure_integration?.last_tested_at || "never"}</div>
            {overview?.azure_integration?.message ? <div><strong>Message:</strong> {overview.azure_integration.message}</div> : null}
          </div>
          {azureActionResult.text ? (
            <div className={azureActionResult.type === "error" ? "pill error" : azureActionResult.type === "warn" ? "pill warn" : "pill"} style={{ marginTop: 10 }}>
              {azureActionResult.text}
            </div>
          ) : null}
          <div className="toolbar-row" style={{ marginTop: 10 }}>
            <input
              value={azure.tenant_id}
              onChange={(e) => setAzure((prev) => ({ ...prev, tenant_id: e.target.value }))}
              placeholder="Tenant ID"
            />
            <input
              value={azure.client_id}
              onChange={(e) => setAzure((prev) => ({ ...prev, client_id: e.target.value }))}
              placeholder="Client ID"
            />
          </div>
          <div className="toolbar-row" style={{ marginTop: 10 }}>
            <input
              type="password"
              autoComplete="off"
              value={azure.client_secret}
              onChange={(e) => setAzure((prev) => ({ ...prev, client_secret: e.target.value }))}
              placeholder="Client Secret"
            />
            <input
              value={azure.subscription_id}
              onChange={(e) => setAzure((prev) => ({ ...prev, subscription_id: e.target.value }))}
              placeholder="Subscription ID"
            />
          </div>
          <div className="toolbar-row" style={{ marginTop: 10 }}>
            <button onClick={saveAzure} disabled={busy.azureSave}>
              {busy.azureSave ? "Saving..." : "Save Azure Credentials"}
            </button>
            <button className="dismiss" onClick={runAzureTest} disabled={busy.azureTest}>{busy.azureTest ? "Testing..." : "Test Azure Connection"}</button>
            <button className="danger" onClick={clearAzure} disabled={busy.azureClear}>
              {busy.azureClear ? "Clearing..." : "Clear Azure Credentials"}
            </button>
          </div>
          <div className="pill" style={{ marginTop: 10 }}>Saved Azure secrets are never returned to the UI.</div>
        </section>

        <section className="card">
          <div className="card-title"><h2>Cloud Accounts</h2></div>
          <div className="workspace-stack">
            {CLOUD_ACCOUNT_PROVIDERS.map((provider) => {
              const state = cloudAccountMap[provider.id] || {
                provider: provider.id,
                enabled: false,
                configuration_state: "not_configured",
                connection_state: "not_configured",
                message: "No status available yet.",
              };
              const actionResult = cloudActionResults[provider.id] || { type: "", text: "" };
              return (
                <section key={provider.id} className="card">
                  <div className="card-title"><h3>{provider.label}</h3></div>
                  <div className="status-list">
                    <div><strong>Enabled:</strong> {state.enabled ? "yes" : "no"}</div>
                    <div><strong>Configuration:</strong> {state.configuration_state}</div>
                    <div><strong>Connection:</strong> {state.connection_state}</div>
                    <div><strong>Configured identity:</strong> {state.configured_identity_hint || "n/a"}</div>
                    <div><strong>Authenticated identity:</strong> {state.authenticated_identity || "n/a"}</div>
                    <div><strong>Authenticated name:</strong> {state.authenticated_name || "n/a"}</div>
                    <div><strong>Last tested:</strong> {state.last_tested_at || "never"}</div>
                    {state.message ? <div><strong>Message:</strong> {state.message}</div> : null}
                  </div>
                  {actionResult.text ? (
                    <div className={actionResult.type === "error" ? "pill error" : actionResult.type === "warn" ? "pill warn" : "pill"} style={{ marginTop: 10 }}>
                      {actionResult.text}
                    </div>
                  ) : null}
                  {provider.id === "aws" ? (
                    <>
                      <div className="toolbar-row" style={{ marginTop: 10 }}>
                        <input
                          value={cloudAccounts.aws.access_key_id}
                          onChange={(e) => setCloudAccountValue("aws", "access_key_id", e.target.value)}
                          placeholder="Access Key ID"
                        />
                        <input
                          value={cloudAccounts.aws.region}
                          onChange={(e) => setCloudAccountValue("aws", "region", e.target.value)}
                          placeholder="Region (e.g. us-east-1)"
                        />
                      </div>
                      <div className="toolbar-row" style={{ marginTop: 10 }}>
                        <input
                          type="password"
                          autoComplete="off"
                          value={cloudAccounts.aws.secret_access_key}
                          onChange={(e) => setCloudAccountValue("aws", "secret_access_key", e.target.value)}
                          placeholder="Secret Access Key"
                        />
                      </div>
                    </>
                  ) : (
                    <div style={{ marginTop: 10 }}>
                      <textarea
                        value={cloudAccounts.gcp.service_account_json}
                        onChange={(e) => setCloudAccountValue("gcp", "service_account_json", e.target.value)}
                        placeholder="Paste service account JSON"
                        rows={6}
                        style={{ width: "100%" }}
                      />
                    </div>
                  )}
                  <div className="toolbar-row" style={{ marginTop: 10 }}>
                    <button onClick={() => saveCloudAccount(provider.id)} disabled={busy[`${provider.id}Save`]}>
                      {busy[`${provider.id}Save`] ? "Saving..." : "Save Credentials"}
                    </button>
                    <button className="dismiss" onClick={() => testCloudAccount(provider.id)} disabled={busy[`${provider.id}Test`]}>
                      {busy[`${provider.id}Test`] ? "Testing..." : "Test Connection"}
                    </button>
                    <button className="danger" onClick={() => clearCloudAccount(provider.id)} disabled={busy[`${provider.id}Clear`]}>
                      {busy[`${provider.id}Clear`] ? "Clearing..." : "Clear Credentials"}
                    </button>
                  </div>
                </section>
              );
            })}
          </div>
        </section>

        <section className="card">
          <div className="card-title"><h2>Future Provider Contract</h2></div>
          <div className="status-list">
            <div><strong>Configured contract:</strong> {(overview?.provider_contract || []).join(", ")}</div>
            <div><strong>Scope:</strong> Configuration and connection status foundation only.</div>
          </div>
        </section>
      </section>
    </section>
  );
}