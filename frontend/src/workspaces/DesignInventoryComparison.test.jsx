import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getAzureConnectionStatus, getAzureInventory, listResourceGroups, listResources, listSubscriptions } from "../services/api";
import DesignInventoryComparison from "./DesignInventoryComparison";
import { compareDesignInventory } from "./designInventory";

vi.mock("../services/api", () => ({
  getAzureConnectionStatus: vi.fn(),
  getAzureInventory: vi.fn(),
  listResourceGroups: vi.fn(),
  listResources: vi.fn(),
  listSubscriptions: vi.fn(),
}));

const subscription = "11111111-1111-1111-1111-111111111111";
const other = "22222222-2222-2222-2222-222222222222";
const type = "Microsoft.Compute/virtualMachines";
const subscriptions = [
  { id: "design-sub", subscription_id: subscription, name: "Production" },
  { id: "other-design-sub", subscription_id: other, name: "Disconnected design subscription" },
];
const groups = [
  { id: "design-group", subscription_id: "design-sub", name: "Operations" },
  { id: "other-group", subscription_id: "other-design-sub", name: "Operations" },
];
const vm = (id, name, fields = {}) => ({
  id, name, resource_group_id: "design-group", azure_resource_type: type, ...fields,
});
const armId = (name, sub = subscription, group = "operations") =>
  `/subscriptions/${sub}/resourceGroups/${group}/providers/${type}/${name}`;
const observed = (name, sub = subscription, group = "operations", id = armId(name, sub, group)) =>
  ({ id, name, type, resource_group: group });
const snapshot = {
  subscription_id: subscription,
  status: "synced",
  last_success_at: "2026-11-21T12:00:00Z",
  resources: [observed("prodvm")],
};

beforeEach(() => {
  vi.resetAllMocks();
  listSubscriptions.mockResolvedValue(subscriptions);
  listResourceGroups.mockResolvedValue(groups);
  listResources.mockResolvedValue([vm("resource", "ProdVM"), vm("other-resource", "Omitted VM", {
    resource_group_id: "other-group",
  })]);
  getAzureConnectionStatus.mockResolvedValue({ configured_subscription_ids: [subscription] });
});

describe("Azure inventory comparison", () => {
  it("matches exact root ARM identities and keeps missing, ambiguous, and unsupported distinct", () => {
    const resources = [
      vm("found", "ProdVM"),
      vm("missing", "wrongscope"),
      vm("wrong-group", "wronggroup"),
      vm("child", "prodvm", { parent_resource_id: "found" }),
      vm("child-observation", "nested"),
      vm("duplicate-a", "duplicate"),
      vm("duplicate-b", "DUPLICATE"),
      vm("out-of-scope", "prodvm", { resource_group_id: "other-group" }),
    ];
    const inventory = { ...snapshot, resources: [
      ...snapshot.resources,
      observed("wrongscope", other),
      observed("wronggroup", subscription, "another-group"),
      observed("nested", subscription, "operations", armId("parent") + "/extensions/nested"),
    ] };
    const rows = compareDesignInventory({ subscription, subscriptions, groups, resources, inventory });
    expect(rows.map(({ id, status }) => [id, status])).toEqual([
      ["found", "Matched"],
      ["missing", "Missing from snapshot"],
      ["wrong-group", "Missing from snapshot"],
      ["child", "Unsupported"],
      ["child-observation", "Missing from snapshot"],
      ["duplicate-a", "Ambiguous"],
      ["duplicate-b", "Ambiguous"],
    ]);
    expect(rows[0].observedId).toBe(armId("prodvm"));
  });

  it("shows a retained snapshot and queries only the connected design subscription", async () => {
    getAzureInventory.mockResolvedValue({ ...snapshot, status: "partial_failure" });
    render(<DesignInventoryComparison designId="selected-design" />);
    fireEvent.click(screen.getByRole("button", { name: "Compare Azure inventory" }));
    expect(await screen.findByText(/Stale inventory/)).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getByText("Matched")).toBeInTheDocument();
    expect(within(table).queryByText("Omitted VM")).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Disconnected design subscription/ })).not.toBeInTheDocument();
    expect(listResources).toHaveBeenCalledWith("selected-design");
    expect(getAzureInventory).toHaveBeenCalledTimes(1);
    expect(getAzureInventory).toHaveBeenCalledWith(subscription);
  });

  it("does not label resources missing when no completed snapshot exists", async () => {
    getAzureInventory.mockResolvedValue({ ...snapshot, status: "partial_failure", last_success_at: null });
    render(<DesignInventoryComparison designId="selected-design" />);
    fireEvent.click(screen.getByRole("button", { name: "Compare Azure inventory" }));
    expect(await screen.findByText(/No completed inventory snapshot/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
