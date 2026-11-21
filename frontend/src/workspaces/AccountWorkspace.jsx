import { useState } from "react";
import { changePassword, createClient, createUser, login, resetUserPassword, setClientMember } from "../services/api";

export function SignInForm({ notice, onSignIn }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    setBusy(true);
    setError("");
    try {
      await login(fields.get("username").trim(), fields.get("password"));
      await onSignIn();
    } catch (failure) {
      form.elements.password.value = "";
      setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  return <main className="account-screen">
    <form className="card account-form" onSubmit={submit}>
      <h1>Sign in to MonitorAI</h1>
      {(error || notice) && <div className="error" role="alert">{error || notice}</div>}
      <fieldset disabled={busy}>
        <label>Username<input name="username" autoComplete="username" maxLength={64} required /></label>
        <label>Password<input name="password" type="password" autoComplete="current-password" maxLength={256} required /></label>
        <button type="submit">{busy ? "Signing in…" : "Sign in"}</button>
      </fieldset>
    </form>
  </main>;
}

function AccountForm({ title, action, result, onSubmit, children }) {
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState(null);

  async function submit(event) {
    event.preventDefault();
    const form = event.currentTarget;
    setBusy(true);
    setFeedback(null);
    try {
      await onSubmit(Object.fromEntries(new FormData(form)));
      form.reset();
      if (result) setFeedback({ text: result });
    } catch (error) {
      setFeedback({ error: true, text: error.message });
    } finally {
      setBusy(false);
    }
  }

  return <form className="card account-form" onSubmit={submit}>
    <h2>{title}</h2>
    <fieldset disabled={busy}>
      {children}
      <button type="submit">{busy ? "Saving…" : action}</button>
    </fieldset>
    {feedback && <div className={feedback.error ? "error" : ""} role={feedback.error ? "alert" : "status"}>{feedback.text}</div>}
  </form>;
}

export function AccountWorkspace({ user, client, onMembershipChange, onPasswordChanged }) {
  const canManageMembers = client && user.is_platform_admin;

  return <section className="workspace-panel">
    <h1>Account</h1>
    <p>Signed in as <strong>{user.username}</strong>{user.is_platform_admin && " · Platform administrator"}</p>
    {client ? <p>Active client <strong>{client.client_name}</strong> · {client.role}</p> : <p>No client access assigned.</p>}
    <div className="grid account-grid">
      <AccountForm title="Change password" action="Change password" onSubmit={async (values) => {
        await changePassword(values);
        onPasswordChanged();
      }}>
        <label>Current password<input name="current_password" type="password" autoComplete="current-password" maxLength={256} required /></label>
        <label>New password<input name="new_password" type="password" autoComplete="new-password" minLength={12} maxLength={256} required /></label>
      </AccountForm>
      {user.is_platform_admin && <>
        <AccountForm title="Create client" action="Create client" result="Client created." onSubmit={async ({ name }) => {
          await createClient({ name: name.trim() });
          await onMembershipChange();
        }}>
          <label>Client name<input name="name" maxLength={160} required /></label>
        </AccountForm>
        <AccountForm title="Create user" action="Create user" result="User created." onSubmit={({ username, password }) => createUser({ username: username.trim(), password })}>
          <label>New username<input name="username" autoComplete="off" maxLength={64} required /></label>
          <label>Initial password<input name="password" type="password" autoComplete="new-password" minLength={12} maxLength={256} required /></label>
        </AccountForm>
        <AccountForm title="Reset user password" action="Reset password" result="Password reset." onSubmit={({ username, new_password }) => resetUserPassword(username.trim(), { new_password })}>
          <label>Username to reset<input name="username" autoComplete="off" maxLength={64} required /></label>
          <label>Replacement password<input name="new_password" type="password" autoComplete="new-password" minLength={12} maxLength={256} required /></label>
        </AccountForm>
      </>}
      {canManageMembers && <AccountForm title={`Manage access for ${client.client_name}`} action="Save membership" result="Membership saved." onSubmit={async ({ username, role }) => {
        await setClientMember(client.client_id, { username: username.trim(), role });
        await onMembershipChange();
      }}>
        <label>Member username<input name="username" autoComplete="off" maxLength={64} required /></label>
        <label>Client role<select name="role">
          <option value="viewer">Viewer</option>
          <option value="editor">Editor</option>
          <option value="admin">Administrator</option>
        </select></label>
      </AccountForm>}
    </div>
  </section>;
}
