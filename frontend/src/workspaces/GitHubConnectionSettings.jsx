import { useEffect, useState } from "react";
import { clearGitHubConnection, getGitHubConnection, saveGitHubConnection } from "../services/api";

export default function GitHubConnectionSettings({ onSaved }) {
  const [connection, setConnection] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  useEffect(() => {
    let active = true;
    getGitHubConnection().then((value) => {
      if (active) setConnection(value);
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") setError(failure.message);
    });
    return () => { active = false; };
  }, []);

  async function save(event) {
    event.preventDefault();
    const form = event.currentTarget;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const value = await saveGitHubConnection(Object.fromEntries(new FormData(form)));
      setConnection(value);
      onSaved(value);
      form.reset();
      setMessage("GitHub connection saved.");
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  async function clear() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await clearGitHubConnection();
      setConnection(null);
      onSaved(null);
      setMessage("GitHub connection removed.");
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  return <section className="card account-form">
    <h2>GitHub connection</h2>
    {connection && <p>Configured repository {connection.owner}/{connection.repository}</p>}
    <p>Use a repository-scoped GitHub token with read access to Actions.</p>
    <form className="account-form" onSubmit={save}>
      <fieldset disabled={busy} key={connection && `${connection.owner}/${connection.repository}`}>
        <label>Configured repository owner<input name="owner" defaultValue={connection?.owner} maxLength={39} required /></label>
        <label>Configured repository name<input name="repository" defaultValue={connection?.repository} maxLength={100} required /></label>
        <label>GitHub token<input name="token" autoComplete="new-password" type="password" required /></label>
        <div className="actions">
          <button type="submit">Save connection</button>
          {connection && <button type="button" className="dismiss" onClick={clear}>Remove connection</button>}
        </div>
      </fieldset>
    </form>
    {error && <p className="error" role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
  </section>;
}
