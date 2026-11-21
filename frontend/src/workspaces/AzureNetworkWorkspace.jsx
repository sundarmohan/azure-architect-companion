import { useMemo, useState } from "react";
import { Background, Controls, MarkerType, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { getAzureNetwork, refreshAzureNetwork } from "../services/api";
import AzureSnapshotWorkspace, { displayLabel } from "./AzureSnapshotWorkspace";

const MAX_TOPOLOGY_NEIGHBORS = 16;
const PAGE_SIZE = 20;

function resourceName(id, resourcesById) {
  return resourcesById.get(id)?.name || String(id).split("/").filter(Boolean).at(-1) || "Unknown resource";
}

function RelatedTopology({ selected, links, resourcesById }) {
  const { nodes, edges, omitted } = useMemo(() => {
    const neighborIds = [...new Set(links.map((link) => link.source === selected.id ? link.target : link.source))]
      .filter((id) => id !== selected.id);
    const visible = neighborIds.slice(0, MAX_TOPOLOGY_NEIGHBORS);
    const nodeIds = new Set([selected.id, ...visible]);
    const nodes = [
      { id: selected.id, position: { x: 270, y: Math.max(0, (Math.ceil(visible.length / 2) - 1) * 50) },
        data: { label: selected.name }, className: "observability-selected-node" },
      ...visible.map((id, index) => ({
        id, position: { x: index % 2 === 0 ? 0 : 540, y: Math.floor(index / 2) * 100 },
        data: { label: resourceName(id, resourcesById) },
      })),
    ];
    const edges = links.filter(({ source, target }) => nodeIds.has(source) && nodeIds.has(target))
      .map(({ source, target, kind }, index) => ({
        id: `${source}-${target}-${kind}-${index}`, source, target,
        markerEnd: { type: MarkerType.ArrowClosed },
      }));
    return { nodes, edges, omitted: neighborIds.length - visible.length };
  }, [links, resourcesById, selected]);

  if (!links.length) return <p>No configuration links were returned for this resource.</p>;
  return <>
    <div className="observability-topology" aria-label={`Configuration topology for ${selected.name}`}>
      <ReactFlow key={selected.id} nodes={nodes} edges={edges} fitView
        nodesDraggable={false} nodesConnectable={false} elementsSelectable={false} deleteKeyCode={null}>
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
    {omitted > 0 && <p>{omitted} additional related resources are listed in the relationship table.</p>}
  </>;
}

function NetworkLinks({ links, resourcesById }) {
  const [page, setPage] = useState(0);
  if (!links.length) return null;
  const pages = Math.ceil(links.length / PAGE_SIZE);
  const current = Math.min(page, pages - 1);
  return <div className="account-form">
    <h3>Configuration relationships ({links.length})</h3>
    <div className="design-table"><table className="table">
      <thead><tr><th scope="col">Source</th><th scope="col">Relationship</th><th scope="col">Target</th></tr></thead>
      <tbody>{links.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE).map((link, index) => (
        <tr key={`${link.source}-${link.target}-${link.kind}-${index}`}>
          <td title={link.source}>{resourceName(link.source, resourcesById)}</td>
          <td>{displayLabel(link.kind)}</td>
          <td title={link.target}>{resourceName(link.target, resourcesById)}</td>
        </tr>
      ))}</tbody>
    </table></div>
    {pages > 1 && <div className="actions">
      <button disabled={current === 0} onClick={() => setPage(current - 1)}>Previous</button>
      <span aria-live="polite">Page {current + 1} of {pages}</span>
      <button disabled={current >= pages - 1} onClick={() => setPage(current + 1)}>Next</button>
    </div>}
  </div>;
}

function configurationValue(value) {
  if (value === null || value === undefined) return "Unknown";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function NetworkResources({ snapshot }) {
  const [filter, setFilter] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const resources = snapshot.resources;
  const query = filter.trim().toLowerCase();
  const resourcesById = useMemo(() => new Map(resources.map((resource) => [resource.id, resource])), [resources]);
  const matching = useMemo(() => resources.filter((resource) => !query ||
    [resource.name, resource.type, resource.location].some((value) => value?.toLowerCase().includes(query))), [query, resources]);
  const selected = matching.find(({ id }) => id === selectedId) || matching[0];
  const links = useMemo(() => selected
    ? snapshot.links.filter(({ source, target }) => source === selected.id || target === selected.id)
    : [], [snapshot.links, selected]);
  const properties = Object.entries(selected?.properties || {});

  return <section className="card account-form">
    <h2>Network resources ({resources.length})</h2>
    {snapshot.limitations?.length > 0 && <>
      <h3>Collection limits</h3>
      <ul>{snapshot.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
    </>}
    {resources.length > 0 && <label>Filter network resources<input value={filter}
      onChange={(event) => setFilter(event.target.value)} placeholder="Name, resource type, or location" /></label>}
    {matching.length > 0 && <label>Resource<select value={selected.id} onChange={(event) => setSelectedId(event.target.value)}>
      {matching.map((resource) => <option key={resource.id} value={resource.id}>{resource.name} · {resource.type}</option>)}
    </select></label>}
    {selected ? <div className="account-form">
      <h3>{selected.name}</h3>
      <dl className="design-meta">
        <div><dt>Resource type</dt><dd>{selected.type || "Unknown"}</dd></div>
        <div><dt>Location</dt><dd>{selected.location || "Unknown"}</dd></div>
      </dl>
      <details className="network-properties">
        <summary>Azure configuration</summary>
        {properties.length ? <dl>
          {properties.map(([name, value]) => <div key={name}>
            <dt>{displayLabel(name.replace(/([a-z])([A-Z])/g, "$1 $2"))}</dt>
            <dd>{value && typeof value === "object" ? <pre>{JSON.stringify(value, null, 2)}</pre> : configurationValue(value)}</dd>
          </div>)}
        </dl> : <p>No configuration details were returned.</p>}
      </details>
      <RelatedTopology selected={selected} links={links} resourcesById={resourcesById} />
      <NetworkLinks key={selected.id} links={links} resourcesById={resourcesById} />
    </div> : <p>{resources.length ? "No resources match the filter." : "No network resources have been collected."}</p>}
  </section>;
}

export default function AzureNetworkWorkspace({ canRefresh }) {
  return <AzureSnapshotWorkspace title="Network Intelligence"
    description="Inspect Azure network configuration and relationships from the selected subscription."
    canRefresh={canRefresh} loadSnapshot={getAzureNetwork} refreshSnapshot={refreshAzureNetwork}>
    {(snapshot) => snapshot && <NetworkResources snapshot={snapshot} />}
  </AzureSnapshotWorkspace>;
}
