import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { getAzureConnectionStatus, getAzureInventory, getAzureMonitoring, getAzureSecurity, getAzureHealthIncidents, getComplianceReviews } from "../services/api";
import PlatformDashboard from "./PlatformDashboard";

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
    resources: [{ health: "degraded", health_status: "synced" }, { health: "unknown", health_status: "synced" }],
  });
  getAzureSecurity.mockRejectedValue(new Error("Unavailable"));
  getAzureHealthIncidents.mockResolvedValue({ incidents: [{ status: "open" }], has_next: true });
  getComplianceReviews.mockResolvedValue([{ state: "action_required" }]);
  render(<PlatformDashboard clientName="Operations" onOpen={onOpen} />);

  expect(await screen.findByText("1 of 2")).toBeInTheDocument();
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
