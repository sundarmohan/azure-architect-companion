import { useCallback, useEffect, useRef, useState } from "react";
import ArchitectureWorkspace from "./workspaces/ArchitectureWorkspace";
import AzureConnectionWorkspace from "./workspaces/AzureConnectionWorkspace";
import AzureInventoryWorkspace from "./workspaces/AzureInventoryWorkspace";
import { AccountWorkspace, SignInForm } from "./workspaces/AccountWorkspace";
import { getCurrentUser, logout, onUnauthorized, setApiSession } from "./services/api";
import "./styles/app.css";
import "./styles/platform.css";
import "./styles/account.css";

export default function App() {
  const [user, setUser] = useState(null);
  const [clientId, setClientId] = useState("");
  const [workspace, setWorkspace] = useState("architecture");
  const [checking, setChecking] = useState(true);
  const [signingOut, setSigningOut] = useState(false);
  const [notice, setNotice] = useState("");
  const currentClient = useRef("");
  const sessionVersion = useRef(0);

  const selectClient = useCallback((id) => {
    if (currentClient.current === id) return;
    currentClient.current = id;
    setApiSession(id);
    setClientId(id);
  }, []);

  const endSession = useCallback((message = "") => {
    sessionVersion.current += 1;
    currentClient.current = "";
    setApiSession();
    setClientId("");
    setUser(null);
    setWorkspace("architecture");
    setNotice(message);
  }, []);

  const refreshUser = useCallback(async () => {
    const version = sessionVersion.current;
    const account = await getCurrentUser();
    if (version !== sessionVersion.current) return;
    const client = account.memberships.find((item) => item.client_id === currentClient.current) || account.memberships[0];
    selectClient(client?.client_id || "");
    setUser(account);
  }, [selectClient]);

  const checkSession = useCallback(async () => {
    setChecking(true);
    setNotice("");
    try {
      await refreshUser();
    } catch (error) {
      endSession(error.status === 401 ? "" : error.message);
    } finally {
      setChecking(false);
    }
  }, [endSession, refreshUser]);

  useEffect(() => {
    const unsubscribe = onUnauthorized(() => endSession("Your session ended. Sign in again."));
    void checkSession();
    return unsubscribe;
  }, [checkSession, endSession]);

  async function signOut() {
    setSigningOut(true);
    setNotice("");
    try {
      await logout();
      endSession();
    } catch (error) {
      if (error.status !== 401) setNotice(error.message);
    } finally {
      setSigningOut(false);
    }
  }

  if (checking) return <main className="account-screen" role="status">Checking your session…</main>;
  if (!user) return <SignInForm notice={notice} onSignIn={async () => {
    await refreshUser();
    setNotice("");
  }} />;

  const activeClient = user.memberships.find((item) => item.client_id === clientId);
  const canEdit = activeClient?.role === "admin" || activeClient?.role === "editor";

  return (
    <div className="app-shell">
      <aside className="app-nav">
        <div className="brand">MONITORAI PLATFORM</div>
        <nav className="nav-list" aria-label="Workspace navigation">
          {activeClient && <>
            <button className={`nav-item ${workspace === "architecture" ? "active" : ""}`} onClick={() => setWorkspace("architecture")}>Architecture Studio</button>
            <button className={`nav-item ${workspace === "inventory" ? "active" : ""}`} onClick={() => setWorkspace("inventory")}>Azure Inventory</button>
            <button className={`nav-item ${workspace === "azure" ? "active" : ""}`} onClick={() => setWorkspace("azure")}>Azure Connection</button>
          </>}
          <button className={`nav-item ${workspace === "account" ? "active" : ""}`} onClick={() => setWorkspace("account")}>Account</button>
        </nav>
        <div className="session-controls">
          {activeClient && <label>
            Client
            <select value={clientId} onChange={(event) => selectClient(event.target.value)}>
              {user.memberships.map((item) => (
                <option key={item.client_id} value={item.client_id}>{item.client_name}</option>
              ))}
            </select>
          </label>}
          <button onClick={signOut} disabled={signingOut}>Sign out</button>
        </div>
      </aside>

      <main className="app-main" key={clientId}>
        {notice && <div className="error" role="alert">{notice}</div>}
        {workspace === "account" || !activeClient ? (
          <AccountWorkspace user={user} client={activeClient} onMembershipChange={refreshUser}
            onPasswordChanged={() => endSession("Password changed. Sign in with your new password.")} />
        ) : workspace === "azure" ? (
          <AzureConnectionWorkspace canManage={activeClient.role === "admin"} />
        ) : workspace === "inventory" ? (
          <AzureInventoryWorkspace canRefresh={canEdit} />
        ) : (
          <ArchitectureWorkspace canEdit={canEdit} canApprove={activeClient.role === "admin"} />
        )}
      </main>
    </div>
  );
}
