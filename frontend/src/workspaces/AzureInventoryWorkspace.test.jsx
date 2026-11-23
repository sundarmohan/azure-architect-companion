import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import AzureInventoryWorkspace from "./AzureInventoryWorkspace";
import { getAzureConnectionStatus, getAzureInventory } from "../services/api";

vi.mock("../services/api", () => ({
  getAzureConnectionStatus: vi.fn(),
  getAzureInventory: vi.fn(),
  refreshAzureInventory: vi.fn(),
}));

it("keeps failed collection and retained evidence visibly distinct", async () => {
  getAzureConnectionStatus.mockResolvedValue({
    configured_subscription_id: "subscription-a",
    configured_subscription_ids: ["subscription-a"],
  });
  getAzureInventory.mockResolvedValue({
    status: "partial_failure",
    failure_stage: "resources",
    failure_reason: "permission_failure",
    correlation_id: "inventory-reference",
    showing_retained_data: true,
    last_attempt_at: "2026-11-23T10:00:00Z",
    last_success_at: "2026-11-22T10:00:00Z",
    resources: [{ id: "one", name: "vm-one", type: "Microsoft.Compute/virtualMachines", resource_group: "rg", location: "eastus" }],
    resource_groups: [],
  });

  render(<AzureInventoryWorkspace canRefresh />);

  expect(await screen.findByText(/Failed stage: resources/)).toBeInTheDocument();
  expect(screen.getByText(/Grant the service principal permission/)).toBeInTheDocument();
  expect(screen.getByText("inventory-reference")).toBeInTheDocument();
  expect(screen.getByText(/Previously collected data is shown below/)).toBeInTheDocument();
  expect(screen.getByText("vm-one")).toBeInTheDocument();
});
