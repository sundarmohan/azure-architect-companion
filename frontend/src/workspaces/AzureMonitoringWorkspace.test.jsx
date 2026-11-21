import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AzureMonitoringWorkspace from "./AzureMonitoringWorkspace";
import {
  getAzureConnectionStatus,
  getAzureMonitoring,
  getAzureMonitoringSchedule,
  refreshAzureMonitoring,
  updateAzureMonitoringSchedule,
} from "../services/api";

vi.mock("../services/api", () => ({
  getAzureConnectionStatus: vi.fn(),
  getAzureMonitoring: vi.fn(),
  refreshAzureMonitoring: vi.fn(),
  getAzureMonitoringSchedule: vi.fn(),
  updateAzureMonitoringSchedule: vi.fn(),
}));

const SUBSCRIPTIONS = ["sub-a", "sub-b"];

function snapshot(name, extra = {}) {
  return {
    status: "synced",
    last_success_at: "2026-11-01T00:00:00Z",
    resources: [{
      id: name,
      name,
      type: "Microsoft.Compute/virtualMachines",
      location: "eastus",
      health: "available",
      health_status: "available",
      metrics_status: "available",
      metrics: [{ name: "Percentage CPU", unit: "Percent", points: [{ timestamp: "2026-11-01T00:00:00Z", value: 0 }] }],
    }],
    ...extra,
  };
}

beforeEach(() => {
  vi.resetAllMocks();
  getAzureConnectionStatus.mockResolvedValue({ configured_subscription_id: SUBSCRIPTIONS[0], configured_subscription_ids: SUBSCRIPTIONS });
});

describe("Azure monitoring workspace", () => {
  it("switches subscriptions without displaying a late response from the earlier selection", async () => {
    let finishEarlier;
    getAzureMonitoring.mockImplementation((id) => {
      if (id === SUBSCRIPTIONS[0]) return new Promise((resolve) => { finishEarlier = resolve; });
      return Promise.resolve(snapshot("vm-b"));
    });
    render(<AzureMonitoringWorkspace canRefresh />);

    const selector = await screen.findByLabelText("Subscription");
    await waitFor(() => expect(getAzureMonitoring).toHaveBeenCalledWith(SUBSCRIPTIONS[0]));
    fireEvent.change(selector, { target: { value: SUBSCRIPTIONS[1] } });
    await screen.findByRole("heading", { name: "vm-b" });
    await act(async () => finishEarlier(snapshot("vm-a")));

    expect(screen.queryByRole("heading", { name: "vm-a" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "vm-b" })).toBeInTheDocument();
  });

  it("keeps the previous metrics visible after a failed refresh and preserves a real zero sample", async () => {
    getAzureMonitoring.mockResolvedValue(snapshot("vm-a"));
    refreshAzureMonitoring.mockResolvedValue(snapshot("vm-a", {
      status: "partial_failure",
      failure_reason: "permission_failure",
      last_attempt_at: "2026-11-01T01:00:00Z",
    }));
    render(<AzureMonitoringWorkspace canRefresh />);

    await screen.findByRole("heading", { name: "vm-a" });
    fireEvent.click(screen.getByRole("button", { name: "Refresh snapshot" }));
    expect(await screen.findByText("Showing the last available data.")).toBeInTheDocument();
    expect(screen.getByText("The Azure connection lacks permission to collect this data.")).toBeInTheDocument();
    expect(screen.getAllByText("0 Percent").length).toBeGreaterThan(0);
    expect(refreshAzureMonitoring).toHaveBeenCalledWith(SUBSCRIPTIONS[0]);
  });

  it("shows the inventory prerequisite to viewers without refresh or schedule controls", async () => {
    getAzureMonitoring.mockResolvedValue(snapshot("", { status: "inventory_required", last_success_at: null, resources: [] }));
    render(<AzureMonitoringWorkspace canRefresh={false} canManageSchedule={false} />);

    expect(await screen.findByText(/Refresh Azure Inventory for this subscription/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Refresh snapshot" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Collection schedule" })).not.toBeInTheDocument();
    expect(getAzureMonitoringSchedule).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Reload saved snapshot" }));
    await waitFor(() => expect(getAzureMonitoring).toHaveBeenCalledTimes(2));
    expect(refreshAzureMonitoring).not.toHaveBeenCalled();
  });

  it("saves the collection schedule for the selected subscription as an administrator", async () => {
    getAzureMonitoring.mockResolvedValue(snapshot("vm-a"));
    getAzureMonitoringSchedule.mockResolvedValue({ enabled: false, interval_minutes: 60, next_run_at: null });
    updateAzureMonitoringSchedule.mockResolvedValue({ enabled: true, interval_minutes: 30, next_run_at: "2026-11-01T01:00:00Z" });
    render(<AzureMonitoringWorkspace canRefresh canManageSchedule />);

    fireEvent.click(await screen.findByLabelText("Enable scheduled collection"));
    fireEvent.change(screen.getByLabelText("Interval (minutes)"), { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "Save schedule" }));

    expect(await screen.findByText("Schedule saved.")).toBeInTheDocument();
    expect(updateAzureMonitoringSchedule).toHaveBeenCalledWith(SUBSCRIPTIONS[0], { enabled: true, interval_minutes: 30 });
  });
});
