import { useEffect, useState } from "react";
import { getAzureConnectionStatus, getAzureInventory, listResourceGroups, listResources, listSubscriptions } from "../services/api";
import { comparableSubscriptions, compareDesignInventory } from "./designInventory";

function InventoryComparison({ subscription, design }) {
  const [inventory, setInventory] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    getAzureInventory(subscription).then((data) => {
      if (active) setInventory(data);
    }).catch((failure) => {
      if (active && failure.name !== "AbortError") setFailed(true);
    });
    return () => { active = false; };
  }, [subscription]);

  if (failed) return <p className="error" role="alert">The inventory snapshot could not be loaded. Reload comparison to retry.</p>;
  if (!inventory) return <p role="status">Reading the saved Azure inventory…</p>;

  const rows = compareDesignInventory({ subscription, inventory, ...design });
  if (!rows) return <p>No completed inventory snapshot is available for this subscription. Resource presence cannot be assessed.</p>;

  return <>
    <p>Last completed snapshot <time dateTime={inventory.last_success_at}>
      {new Date(inventory.last_success_at).toLocaleString()}
    </time>.</p>
    {inventory.status !== "synced" && <p role="status">Stale inventory. The latest refresh did not complete. Results use the last completed snapshot.</p>}
    {rows.length === 0 ? <p>No design resources are assigned to resource groups in this subscription.</p>
      : <div className="design-table"><table className="table" aria-label="Design resources compared with Azure inventory">
        <thead><tr>
          <th scope="col">Design resource</th>
          <th scope="col">Resource group</th>
          <th scope="col">ARM type</th>
          <th scope="col">Snapshot result</th>
          <th scope="col">Observed ARM ID</th>
        </tr></thead>
        <tbody>{rows.map((row) => <tr key={row.id}>
          <td>{row.name}</td><td>{row.group}</td><td>{row.type || "—"}</td><td>{row.status}</td>
          <td>{row.observedId || "—"}</td>
        </tr>)}</tbody>
      </table></div>}
  </>;
}

export default function DesignInventoryComparison({ designId }) {
  const [data, setData] = useState(null);
  const [subscription, setSubscription] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    setData(null);
    try {
      const [subscriptions, groups, resources, connection] = await Promise.all([
        listSubscriptions(designId), listResourceGroups(designId), listResources(designId), getAzureConnectionStatus(),
      ]);
      const choices = comparableSubscriptions(subscriptions, connection);
      setSubscription((previous) => choices.some(({ id }) => id === previous) ? previous : choices[0]?.id || "");
      setData({ subscriptions, groups, resources, choices });
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure.message);
    } finally {
      setLoading(false);
    }
  }

  return <section className="card account-form">
    <h2>Azure inventory comparison</h2>
    <p>Only resources attached to a design resource group mapped to the selected subscription are evaluated. Matching top-level resources requires the same resource group, ARM type, and name in the last completed snapshot.</p>
    <div><button type="button" disabled={loading} onClick={load}>{data || error ? "Reload comparison" : "Compare Azure inventory"}</button></div>
    {loading && <p role="status">Loading design scope…</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {data && !data.choices.length && <p>No subscription in this design matches a subscription configured on the client’s Azure connection.</p>}
    {data && subscription && <>
      <label>Design subscription<select value={subscription} onChange={(event) => setSubscription(event.target.value)}>
        {data.choices.map(({ id, name }) => <option key={id} value={id}>{name} ({id})</option>)}
      </select></label>
      <InventoryComparison key={subscription} subscription={subscription} design={data} />
    </>}
  </section>;
}
