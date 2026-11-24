import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { getAzureConnectionStatus, getAzureInventory, getAzureMonitoring, getAzureSecurity, getAzureHealthIncidents, getComplianceReviews } from "../services/api";
import PlatformDashboard, { getPriorities } from "./PlatformDashboard";

vi.mock("../services/api", () => ({
  getAzureConnectionStatus: vi.fn(),
  getAzureInventory: vi.fn(),
  getAzureMonitoring: vi.fn(),
  getAzureSecurity: vi.fn(),
  getAzureHealthIncidents: vi.fn(),
  getComplianceReviews: vi.fn(),
}));

it("loads the selected subscription, keeps unavailable sources distinct, and links to the source workspace", async () => {
  const onOpen = vi.fn();
  getAzureConnectionStatus.mockResolvedValue({ configured_subscription_ids: ["sub-a", "sub-b"] });
  getAzureInventory.mockResolvedValue({ status: "not_synced", resources: [] });
  getAzureMonitoring.mockResolvedValue({
    status: "synced",
    resources: [
      { id: "vm", name: "vm", health: "degraded", health_status: "synced" },
      { id: "other-vm", health: "unknown", health_status: "synced" },
    ],
  });
  getAzureSecurity.mockRejectedValue(new Error("Unavailable"));
  getAzureHealthIncidents.mockResolvedValue({ incidents: [{ id: "incident-1", resource_id: "other-vm", status: "open" }], has_next: true });
  getComplianceReviews.mockResolvedValue([{ state: "action_required" }]);
  render(<PlatformDashboard clientName="Operations" onOpen={onOpen} />);

  expect(await screen.findByText("1 of 2")).toBeInTheDocument();
  expect(screen.getByRole("table", { name: "Evidence-backed priorities" })).toBeInTheDocument();
  expect(screen.getByText("Inventory collection requires attention")).toBeInTheDocument();
  expect(screen.getByText("vm is degraded")).toBeInTheDocument();
  expect(screen.getByText("Saved evidence could not be loaded.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Security" }));
  expect(onOpen).toHaveBeenCalledWith("security");
  fireEvent.change(screen.getByLabelText("Subscription"), { target: { value: "sub-b" } });
  expect(await screen.findByText("1 of 2")).toBeInTheDocument();
  expect(getAzureHealthIncidents.mock.calls).toEqual([["sub-a", 1], ["sub-b", 1]]);
  for (const load of [getAzureInventory, getAzureMonitoring, getAzureSecurity, getAzureHealthIncidents, getComplianceReviews]) {
    expect(load.mock.calls.map(([id]) => id)).toEqual(["sub-a", "sub-b"]);
  }
});

it("derives owners and due state only from stored workflow evidence", () => {
  const priorities = getPriorities({
    inventory: { status: "synced", last_success_at: "2026-11-24T00:00:00Z" },
    monitoring: { status: "synced", last_success_at: "2026-11-24T00:00:00Z", resources: [] },
    security: { status: "synced", last_success_at: "2026-11-24T00:00:00Z", findings: [{
      id: "finding", title: "Restrict public access", source: "azure_configuration", severity: "high",
      observed_at: "2026-11-24T00:00:00Z", tracking: { status: "in_progress", owner: "Security", due_date: "2026-12-31" },
    }] },
    incidents: { incidents: [] },
    compliance: [{ topic: "hipaa", state: "action_required", action: "Collect evidence", owner: null, due_date: null }],
  });

  expect(priorities.find(({ id }) => id === "security-finding").owner).toBe("Security");
  expect(priorities.find(({ id }) => id === "compliance-hipaa").owner).toBe("Unassigned");
});
