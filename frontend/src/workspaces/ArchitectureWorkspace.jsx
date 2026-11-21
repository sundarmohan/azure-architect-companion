import { useEffect, useState } from "react";
import {
  listArchitectures,
  createArchitecture,
  updateArchitecture,
  deleteArchitecture,
  duplicateArchitecture,
} from "../services/api";
import Designer from "../Designer";
import DesignDetails, { designStatus } from "./DesignDetails";
import "../styles/design.css";

function ArchitectureFormModal({ title, design, duplicate, onSubmit, onClose, isSubmitting = false, error }) {
  async function submit(event) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    const name = values.name.trim();
    if (!name || isSubmitting) return;
    await onSubmit(duplicate ? { name } : {
      name,
      project: values.project.trim() || null,
      environment: values.environment.trim() || "draft",
      default_region: values.default_region.trim() || null,
      description: values.description.trim() || null,
    });
  }

  return (
    <div className="modal-backdrop">
      <form className="modal-card account-form" role="dialog" aria-modal="true" aria-label={title} onSubmit={submit}>
        <h2>{title}</h2>
        <fieldset disabled={isSubmitting}>
          <label>Architecture name<input name="name" autoFocus defaultValue={duplicate ? `${design.name} copy`.slice(0, 200) : design?.name} maxLength={200} required /></label>
          {!duplicate && <>
            <label>Project<input name="project" defaultValue={design?.project || ""} maxLength={160} /></label>
            <label>Environment<input name="environment" defaultValue={design?.environment || ""} maxLength={50} /></label>
            <label>Default Azure region<input name="default_region" defaultValue={design?.default_region || ""} placeholder="eastus" /></label>
            <label>Description<textarea name="description" defaultValue={design?.description || ""} rows={3} /></label>
          </>}
        </fieldset>
        {error && <div className="error" role="alert">{error}</div>}
        <div className="actions">
          <button type="button" className="dismiss" disabled={isSubmitting} onClick={onClose}>Cancel</button>
          <button type="submit" disabled={isSubmitting}>{isSubmitting ? "Saving…" : "Save"}</button>
        </div>
      </form>
    </div>
  );
}

export default function ArchitectureWorkspace({ canEdit, canApprove }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [active, setActive] = useState(null);
  const [showDesigner, setShowDesigner] = useState(false);
  const [form, setForm] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [filter, setFilter] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      setItems(await listArchitectures());
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setLoading(false);
    }
  }

  function openForm(mode, design) {
    setForm({ mode, design });
    setFormError("");
  }

  function openDesign(design, canvas = false) {
    setActive(design);
    setShowDesigner(canvas);
  }

  async function save(values) {
    setSubmitting(true);
    setFormError("");
    try {
      let design;
      if (form.mode === "edit") design = await updateArchitecture(form.design.id, values);
      else if (form.mode === "duplicate") design = await duplicateArchitecture(form.design.id, values);
      else design = await createArchitecture(values);
      openDesign(design);
      setForm(null);
      await load();
    } catch (failure) {
      if (failure.name !== "AbortError") setFormError(failure.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function remove(design) {
    if (!window.confirm(`Delete "${design.name}" permanently?`)) return;
    try {
      await deleteArchitecture(design.id);
      setActive(null);
      await load();
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  if (active && showDesigner) {
    return (
      <section className="workspace-panel">
        <div className="workspace-header">
          <div>
            <div className="workspace-eyebrow">Architecture</div>
            <h1>Architecture Studio</h1>
            <p>View the topology and edit draft designs.</p>
          </div>
        </div>
        <div className="designer-host">
          <Designer architecture={active} scopedAzure canEdit={canEdit && active.status === "draft"}
            canEstimate={canEdit} onBack={() => setShowDesigner(false)} />
        </div>
      </section>
    );
  }

  const query = filter.trim().toLowerCase();
  const matches = items.filter((item) => [item.name, item.project, item.environment, designStatus(item.status)]
    .some((value) => value?.toLowerCase().includes(query)));
  const formTitle = { create: "New architecture", edit: "Edit design details", duplicate: "Duplicate design" };

  return (
    <section className="workspace-panel">
      <div className="workspace-header">
        <div>
          <div className="workspace-eyebrow">Architecture</div>
          <h1>Architecture Studio</h1>
          <p>Design Azure topology, review changes, and export architecture artifacts.</p>
        </div>
      </div>

      {error && <div className="error" role="alert">{error}</div>}

      {active ? <DesignDetails key={active.id} design={active} canEdit={canEdit} canApprove={canApprove}
        onBack={() => { setActive(null); void load(); }}
        onOpenDesigner={() => setShowDesigner(true)}
        onEdit={() => openForm("edit", active)}
        onDuplicate={() => openForm("duplicate", active)}
        onDelete={() => remove(active)}
        onUpdate={setActive} /> : <section className="card">
        <div className="card-title"><h2>Architecture Designs</h2><div className="actions"><span>{items.length}</span>{canEdit && <button onClick={() => openForm("create")}>New architecture</button>}</div></div>
        {items.length > 0 && <label className="design-control">Filter designs<input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Name, project, environment, or status" /></label>}
        {loading && items.length === 0 ? (
          <p role="status">Loading…</p>
        ) : items.length === 0 ? (
          <div className="empty">{canEdit ? "No architectures yet. Create your first design." : "No architectures yet."}</div>
        ) : matches.length === 0 ? (
          <p>No matching designs.</p>
        ) : (
          <div className="grid">
            {matches.map((a) => (
              <article className="architecture" key={a.id}>
                <h3>{a.name}</h3>
                <p>{designStatus(a.status)}</p>
                <small>{a.provider || "azure"} • {a.environment || "draft"}</small>
                <div className="actions">
                  <button onClick={() => openDesign(a)}>Manage design</button>
                  <button className="dismiss" onClick={() => openDesign(a, true)}>Open designer</button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>}

      {canEdit && form && (
        <ArchitectureFormModal
          title={formTitle[form.mode]}
          design={form.design}
          duplicate={form.mode === "duplicate"}
          onSubmit={save}
          onClose={() => setForm(null)}
          isSubmitting={submitting}
          error={formError}
        />
      )}
    </section>
  );
}
