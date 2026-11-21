import { useEffect, useState } from "react";
import {
  listArchitectures,
  createArchitecture,
  updateArchitecture,
  deleteArchitecture,
  listAzureSubscriptionInventory,
} from "../services/api";
import Designer from "../Designer";

function ArchitectureFormModal({ title, initialValue, onSubmit, onClose, isSubmitting = false }) {
  const [name, setName] = useState(initialValue || "");
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <h3>{title}</h3>
        <label htmlFor="architecture-name">Architecture name</label>
        <input
          id="architecture-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Enter architecture name"
        />
        <div className="actions">
          <button className="dismiss" onClick={onClose}>Cancel</button>
          <button
            disabled={isSubmitting}
            onClick={async () => {
              if (isSubmitting) return;
              const trimmed = name.trim();
              if (!trimmed) return;
              await onSubmit(trimmed);
            }}
          >
            {isSubmitting ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ArchitectureWorkspace() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [inventoryLoading, setInventoryLoading] = useState(true);
  const [error, setError] = useState("");
  const [active, setActive] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState(null);
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [renameSubmitting, setRenameSubmitting] = useState(false);
  const [subscriptionInventory, setSubscriptionInventory] = useState([]);

  async function load() {
    setLoading(true);
    setInventoryLoading(true);
    setError("");
    await Promise.all([
      listArchitectures()
        .then(setItems)
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false)),
      listAzureSubscriptionInventory()
        .then(setSubscriptionInventory)
        .catch((e) => setError(e.message))
        .finally(() => setInventoryLoading(false)),
    ]);
  }

  async function create(name) {
    if (createSubmitting) return;
    setCreateSubmitting(true);
    try {
      const a = await createArchitecture({ name });
      setCreateOpen(false);
      setActive(a);
      void load();
    } catch (e) {
      setError(e.message);
    } finally {
      setCreateSubmitting(false);
    }
  }

  async function rename(name) {
    if (!renameTarget) return;
    if (renameSubmitting) return;
    setRenameSubmitting(true);
    try {
      await updateArchitecture(renameTarget.id, { name });
      setRenameTarget(null);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setRenameSubmitting(false);
    }
  }

  async function remove(a) {
    if (!window.confirm(`Delete "${a.name}"?`)) return;
    try {
      await deleteArchitecture(a.id);
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  if (active) {
    return (
      <section className="workspace-panel">
        <div className="workspace-header">
          <div>
            <div className="workspace-eyebrow">Architecture</div>
            <h1>Architecture Studio</h1>
            <p>Design, organize and persist architecture layouts with hierarchy and discovery.</p>
          </div>
        </div>
        <div className="designer-host">
          <Designer architecture={active} onBack={() => { setActive(null); load(); }} />
        </div>
      </section>
    );
  }

  return (
    <section className="workspace-panel">
      <div className="workspace-header">
        <div>
          <div className="workspace-eyebrow">Architecture</div>
          <h1>Architecture Studio</h1>
          <p>Manage architecture workspaces, then open a design for canvas editing and Azure hierarchy operations.</p>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      <section className="card">
        <div className="card-title"><h2>Architecture Designs</h2><div className="actions"><span>{items.length}</span><button onClick={() => setCreateOpen(true)}>+ New Architecture</button></div></div>
        {loading && items.length === 0 ? (
          <p>Loading...</p>
        ) : items.length === 0 ? (
          <div className="empty">No architectures yet. Create your first design.</div>
        ) : (
          <div className="grid">
            {items.map((a) => (
              <article className="architecture" key={a.id}>
                <h3>{a.name}</h3>
                <p>{a.status}</p>
                <small>{a.provider || "azure"} • {a.environment || "draft"}</small>
                <div className="actions">
                  <button onClick={() => setActive(a)}>Open Designer</button>
                  <button className="dismiss" onClick={() => setRenameTarget(a)}>Rename</button>
                  <button className="danger" onClick={() => remove(a)}>Delete</button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="card">
        <div className="card-title"><h2>Azure Subscription Inventory</h2><span>{subscriptionInventory.length}</span></div>
        {inventoryLoading && subscriptionInventory.length === 0 ? (
          <p>Loading...</p>
        ) : subscriptionInventory.length === 0 ? (
          <div className="empty">No Azure subscriptions are mapped yet. Add credentials in Settings, then create or discover subscriptions in Architecture Studio.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Subscription</th>
                  <th>Tenant</th>
                  <th>Architecture</th>
                  <th>Connection</th>
                  <th>RGs</th>
                  <th>Resources</th>
                  <th>Monitoring</th>
                  <th>HIPAA</th>
                  <th>Last Discovery</th>
                </tr>
              </thead>
              <tbody>
                {subscriptionInventory.map((item) => (
                  <tr key={item.subscription_db_id}>
                    <td>
                      <strong>{item.subscription_name}</strong>
                      <div style={{ color: "#6f7d97", fontSize: 12 }}>{item.subscription_id || "n/a"}</div>
                    </td>
                    <td>{item.tenant_id || "n/a"}</td>
                    <td>{item.architecture_name}</td>
                    <td>{item.connection_state}</td>
                    <td>{item.resource_group_count}</td>
                    <td>{item.resource_count}</td>
                    <td>{item.monitoring_state} ({item.live_resource_count}/{item.monitored_resource_count})</td>
                    <td>{item.hipaa_state}{item.hipaa_score === null ? "" : ` (${item.hipaa_score})`}</td>
                    <td>{item.last_discovery_sync_at || "never"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {createOpen && (
        <ArchitectureFormModal
          title="New Architecture"
          initialValue=""
          onSubmit={create}
          onClose={() => setCreateOpen(false)}
          isSubmitting={createSubmitting}
        />
      )}

      {renameTarget && (
        <ArchitectureFormModal
          title="Rename Architecture"
          initialValue={renameTarget.name}
          onSubmit={rename}
          onClose={() => setRenameTarget(null)}
          isSubmitting={renameSubmitting}
        />
      )}
    </section>
  );
}
