const normalized = (value) => typeof value === "string" ? value.toLowerCase() : "";
const rootType = /^[^/]+\/[^/]+$/;
const rootArmId = /^\/subscriptions\/([^/]+)\/resourcegroups\/([^/]+)\/providers\/([^/]+)\/([^/]+)\/([^/]+)$/;

export function comparableSubscriptions(subscriptions, connection) {
  const ids = connection.configured_subscription_ids?.length
    ? connection.configured_subscription_ids : [connection.configured_subscription_id];
  const allowed = new Set(ids.filter(Boolean).map(normalized));
  const choices = new Map();
  for (const subscription of subscriptions) {
    const id = normalized(subscription.subscription_id);
    if (allowed.has(id) && !choices.has(id)) choices.set(id, subscription.name);
  }
  return Array.from(choices, ([id, name]) => ({ id, name }));
}

export function compareDesignInventory({ subscription, subscriptions, groups, resources, inventory }) {
  if (!inventory?.last_success_at || normalized(inventory.subscription_id) !== subscription) return null;
  const designSubscriptionIds = new Set(subscriptions
    .filter((item) => normalized(item.subscription_id) === subscription).map((item) => item.id));
  const groupNames = new Map(groups.filter((group) => designSubscriptionIds.has(group.subscription_id))
    .map((group) => [group.id, group.name]));
  const key = (group, type, name) => JSON.stringify([group, type, name].map(normalized));
  const plannedCounts = new Map();
  const observed = new Map();

  for (const resource of inventory.resources) {
    const parts = normalized(resource.id).match(rootArmId);
    if (!parts) continue;
    const [, id, group, provider, kind, name] = parts;
    const type = `${provider}/${kind}`;
    if (id !== subscription || normalized(resource.resource_group) !== group ||
        normalized(resource.type) !== type || normalized(resource.name) !== name) continue;
    const reference = key(group, type, name);
    if (!observed.has(reference)) observed.set(reference, resource.id);
  }

  const rows = resources.filter((resource) => groupNames.has(resource.resource_group_id)).map((resource) => {
    const group = groupNames.get(resource.resource_group_id);
    const type = resource.azure_resource_type;
    const reference = !resource.parent_resource_id && group && rootType.test(type || "") &&
      resource.name && !resource.name.includes("/") ? key(group, type, resource.name) : null;
    if (reference) plannedCounts.set(reference, (plannedCounts.get(reference) || 0) + 1);
    return { id: resource.id, name: resource.name, group, type, reference };
  });

  return rows.map(({ reference, ...row }) => {
    if (!reference) return { ...row, status: "Unsupported", observedId: null };
    const observedId = observed.get(reference) || null;
    const status = plannedCounts.get(reference) > 1 ? "Ambiguous"
      : observedId ? "Matched" : "Missing from snapshot";
    return { ...row, status, observedId };
  });
}
