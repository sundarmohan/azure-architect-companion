import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import MonitoringWorkspace from "./MonitoringWorkspace";

vi.mock("../services/api", () => ({
  getSettingsOverview: vi.fn(),
  listArchitectures: vi.fn(),
  listSubscriptions: vi.fn(),
  listResources: vi.fn(),
  listResourceGroups: vi.fn(),
  getArchitectureMonitoringSummary: vi.fn(),
  getResourceMonitoring: vi.fn(),
  getMonitoringIncidentSummary: vi.fn(),
  getMonitoringAlertSummary: vi.fn(),
  getUnusedResourceSummary: vi.fn(),
  listMonitoringIncidents: vi.fn(),
  getMonitoringIncidentDetail: vi.fn(),
  updateMonitoringIncidentStatus: vi.fn(),
}));

import * as api from "../services/api";

function baseUnusedPayload(overrides = {}) {
  return {
    architecture_id: "arch-1",
    source: "legacy_idle_detector",
    state: "evaluated",
    lookback_days: 7,
    analysis_start_time: "2026-08-24T00:00:00Z",
    analysis_end_time: "2026-08-31T00:00:00Z",
    total_checked: 4,
    total_unused: 3,
    estimated_monthly_waste: 205,
    azure_connection_state: "configured",
    azure_connection_message: "ok",
    message: "Unused resource analysis completed.",
    unused_resources: [
      {
        resource_id: "res-disk",
        resource_name: "disk-unattached",
        resource_type: "microsoft.compute/disks",
        location: "eastus",
        resource_group: "rg-a",
        subscription_id: "sub-ext-1",
        idle_reason: "Managed disk is unattached and not associated with any virtual machine",
        idle_signals: ["config_unattached"],
        confidence: "high",
        recommended_action: "Consider removal",
        days_checked: 7,
        monthly_cost_estimate: 15,
        portal_link: "https://portal.azure.com/#resource/a",
      },
      {
        resource_id: "res-vm",
        resource_name: "vm-prod-01",
        resource_type: "vm",
        location: "eastus",
        resource_group: "rg-a",
        subscription_id: "sub-ext-1",
        idle_reason: "2/2 activity metrics below idle threshold over last 7 days",
        idle_signals: ["cpu_avg_below_5pct(average=2.1)", "network_in_below_100mb(total=12.0)"],
        confidence: "high",
        recommended_action: "Consider resizing",
        days_checked: 7,
        monthly_cost_estimate: 125,
        portal_link: "https://portal.azure.com/#resource/b",
      },
      {
        resource_id: "res-app",
        resource_name: "app-idle-01",
        resource_type: "microsoft.web/sites",
        location: "eastus",
        resource_group: "rg-b",
        subscription_id: "sub-ext-1",
        idle_reason: "Intermittent usage and limited utilization evidence",
        idle_signals: ["heartbeat_missing"],
        confidence: "medium",
        recommended_action: "Review workload requirements",
        days_checked: 7,
        monthly_cost_estimate: 65,
        portal_link: "https://portal.azure.com/#resource/c",
      },
    ],
    ...overrides,
  };
}

async function renderUnusedWorkspace({ unusedPayload, unusedReject = null, subscriptions = null } = {}) {
  api.listArchitectures.mockResolvedValue([{ id: "arch-1", name: "Arch One" }]);
  api.getSettingsOverview.mockResolvedValue({ azure_integration: { connection_state: "configured" } });
  api.listSubscriptions.mockResolvedValue(
    subscriptions || [{ id: "sub-db-1", name: "GNX-SERVICE-DEV", subscription_id: "sub-ext-1" }],
  );
  api.listResources.mockResolvedValue([
    {
      id: "res-vm",
      name: "vm-prod-01",
      resource_type: "vm",
      resource_group_id: "rg-1",
      properties: {
        azure_resource_id: "/subscriptions/sub-ext-1/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/vm-prod-01",
      },
    },
    {
      id: "res-app",
      name: "app-idle-01",
      resource_type: "appservice",
      resource_group_id: "rg-2",
      properties: {
        azure_resource_id: "/subscriptions/sub-ext-1/resourceGroups/rg-b/providers/Microsoft.Web/sites/app-idle-01",
      },
    },
    {
      id: "res-disk",
      name: "disk-unattached",
      resource_type: "disk",
      resource_group_id: "rg-1",
      properties: {
        azure_resource_id: "/subscriptions/sub-ext-1/resourceGroups/rg-a/providers/Microsoft.Compute/disks/disk-unattached",
      },
    },
  ]);
  api.listResourceGroups.mockResolvedValue([
    { id: "rg-1", name: "rg-a" },
    { id: "rg-2", name: "rg-b" },
  ]);
  api.getArchitectureMonitoringSummary.mockResolvedValue({
    architecture_id: "arch-1",
    state: "live",
    total_resources: 3,
    monitored_resources: 3,
    live_resources: 3,
    healthy_count: 3,
    warning_count: 0,
    critical_count: 0,
    no_data_count: 0,
    unsupported_count: 0,
    error_count: 0,
    resources: [],
  });
  api.getResourceMonitoring.mockResolvedValue({
    architecture_id: "arch-1",
    resource_id: "res-vm",
    resource_name: "vm-prod-01",
    resource_type: "vm",
    state: "live",
    source: "azure_monitor",
    live: true,
    health_status: "Available",
    metrics: [],
  });
  api.getMonitoringIncidentSummary.mockResolvedValue({ incident_count: 0, incidents: [], critical_count: 0, high_count: 0, medium_count: 0, low_count: 0 });
  api.getMonitoringAlertSummary.mockResolvedValue({ alert_count: 0, alerts: [], critical_count: 0, high_count: 0, medium_count: 0, low_count: 0, open_count: 0, acknowledged_count: 0, resolved_count: 0 });
  api.listMonitoringIncidents.mockResolvedValue([]);
  api.getMonitoringIncidentDetail.mockResolvedValue(null);
  api.updateMonitoringIncidentStatus.mockResolvedValue(null);

  if (unusedReject) {
    api.getUnusedResourceSummary.mockRejectedValue(unusedReject);
  } else {
    api.getUnusedResourceSummary.mockResolvedValue(unusedPayload || baseUnusedPayload());
  }

  render(<MonitoringWorkspace />);

  await waitFor(() => expect(screen.getByRole("tab", { name: "Unused" })).toBeInTheDocument());
  fireEvent.click(screen.getByRole("tab", { name: "Unused" }));
  await waitFor(() => expect(api.getUnusedResourceSummary).toHaveBeenCalled());
}

describe("Monitoring Workspace UI-2C Unused Operations", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("renders unused tab workspace", async () => {
    await renderUnusedWorkspace();
    expect(await screen.findByText("Unused Resource Operations")).toBeInTheDocument();
  });

  it("requests 7-day analysis by default", async () => {
    await renderUnusedWorkspace();
    const call = api.getUnusedResourceSummary.mock.calls.find((entry) => entry?.[1]?.lookback_days === 7);
    expect(call).toBeTruthy();
  });

  it("requests 14-day analysis when selected", async () => {
    await renderUnusedWorkspace();
    const before = api.getUnusedResourceSummary.mock.calls.length;
    fireEvent.change(screen.getByLabelText("Lookback"), { target: { value: "14" } });
    expect(await screen.findByText("Selected analysis period: 14 days")).toBeInTheDocument();
    await waitFor(() => {
      expect(api.getUnusedResourceSummary.mock.calls.length).toBeGreaterThan(before);
    });
  });

  it("requests 30-day analysis when selected", async () => {
    await renderUnusedWorkspace();
    const before = api.getUnusedResourceSummary.mock.calls.length;
    fireEvent.change(screen.getByLabelText("Lookback"), { target: { value: "30" } });
    expect(await screen.findByText("Selected analysis period: 30 days")).toBeInTheDocument();
    await waitFor(() => {
      expect(api.getUnusedResourceSummary.mock.calls.length).toBeGreaterThan(before);
    });
  });

  it("renders KPI cards with real values", async () => {
    await renderUnusedWorkspace();
    expect(screen.getByText("Total resources analyzed")).toBeInTheDocument();
    expect(screen.getByText("Unused resources")).toBeInTheDocument();
    expect(screen.getByText("High-confidence findings")).toBeInTheDocument();
    expect(screen.getByText("Estimated monthly waste")).toBeInTheDocument();
  });

  it("renders unused finding type", async () => {
    await renderUnusedWorkspace();
    expect(screen.getAllByText("Unused").length).toBeGreaterThan(0);
  });

  it("renders idle finding type", async () => {
    await renderUnusedWorkspace();
    expect(screen.getAllByText("Idle").length).toBeGreaterThan(0);
  });

  it("renders low-utilization finding type", async () => {
    await renderUnusedWorkspace();
    expect(screen.getAllByText("Low Utilization").length).toBeGreaterThan(0);
  });

  it("renders confidence values", async () => {
    await renderUnusedWorkspace();
    expect(screen.getAllByText("High").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Medium").length).toBeGreaterThan(0);
  });

  it("renders reason values and fallback", async () => {
    const payload = baseUnusedPayload({
      unused_resources: [
        ...baseUnusedPayload().unused_resources,
        {
          resource_id: "res-rsn",
          resource_name: "reasonless",
          resource_type: "vm",
          location: "eastus",
          resource_group: "rg-z",
          subscription_id: "sub-ext-1",
          idle_reason: "",
          idle_signals: ["heartbeat_missing"],
          confidence: "low",
          recommended_action: null,
          days_checked: 7,
          monthly_cost_estimate: 0,
          portal_link: "https://portal.azure.com/#resource/z",
        },
      ],
    });
    await renderUnusedWorkspace({ unusedPayload: payload });
    expect(screen.getByText("Reason unavailable")).toBeInTheDocument();
  });

  it("renders recommended action values and fallback", async () => {
    const payload = baseUnusedPayload({
      unused_resources: [
        {
          ...baseUnusedPayload().unused_resources[0],
          recommended_action: null,
        },
      ],
    });
    await renderUnusedWorkspace({ unusedPayload: payload });
    expect(screen.getAllByText("Review required").length).toBeGreaterThan(0);
  });

  it("renders estimated waste values", async () => {
    await renderUnusedWorkspace();
    expect(screen.getAllByText("$205.00").length).toBeGreaterThan(0);
  });

  it("supports search filtering", async () => {
    await renderUnusedWorkspace();
    fireEvent.change(screen.getByPlaceholderText("Search findings"), { target: { value: "disk-unattached" } });
    expect(screen.getAllByText("disk-unattached").length).toBeGreaterThan(0);
    expect(screen.queryAllByText("vm-prod-01").length).toBe(0);
  });

  it("supports finding type and confidence filters", async () => {
    await renderUnusedWorkspace();
    fireEvent.change(screen.getByLabelText("Unused finding type filter"), { target: { value: "low_utilization" } });
    fireEvent.change(screen.getByLabelText("Unused confidence filter"), { target: { value: "high" } });
    expect(screen.getAllByText("vm-prod-01").length).toBeGreaterThan(0);
    expect(screen.queryAllByText("app-idle-01").length).toBe(0);
  });

  it("supports clear filters", async () => {
    await renderUnusedWorkspace();
    fireEvent.change(screen.getByPlaceholderText("Search findings"), { target: { value: "disk-unattached" } });
    fireEvent.click(screen.getByRole("button", { name: "Clear unused filters" }));
    expect(screen.getAllByText("vm-prod-01").length).toBeGreaterThan(0);
  });

  it("shows explicit empty state when no findings are detected", async () => {
    await renderUnusedWorkspace({
      unusedPayload: baseUnusedPayload({ total_checked: 3, total_unused: 0, estimated_monthly_waste: 0, unused_resources: [] }),
    });
    expect(screen.getByText("No unused or idle resources detected for this analysis period.")).toBeInTheDocument();
  });

  it("shows API failure state without converting to zero findings", async () => {
    await renderUnusedWorkspace({ unusedReject: new Error("service unavailable") });
    expect(screen.getByText("Unable to complete unused-resource analysis.")).toBeInTheDocument();
    expect(screen.queryByText("$0.00")).not.toBeInTheDocument();
  });

  it("shows unavailable telemetry state", async () => {
    await renderUnusedWorkspace({
      unusedPayload: baseUnusedPayload({ state: "no_data", total_checked: 3, total_unused: 0, unused_resources: [] }),
    });
    expect(screen.getByText("Utilization data unavailable. Try a longer lookback window or verify Azure metric coverage.")).toBeInTheDocument();
  });

  it("shows finding detail with recommendation evidence", async () => {
    await renderUnusedWorkspace();
    expect(screen.getByText("Finding Detail")).toBeInTheDocument();
    expect(screen.getByText("Recommendation mode:")).toBeInTheDocument();
    expect(screen.getByText("Advisory only. No automatic remediation is performed.")).toBeInTheDocument();
  });

  it("navigates to resources tab from View Resource", async () => {
    await renderUnusedWorkspace();
    fireEvent.click(screen.getAllByRole("button", { name: "View Resource" })[0]);
    expect(await screen.findByRole("tab", { name: "Resources", selected: true })).toBeInTheDocument();
  });

  it("navigates to metrics tab from View Metrics", async () => {
    await renderUnusedWorkspace();
    fireEvent.click(screen.getAllByRole("button", { name: "View Metrics" })[0]);
    expect(await screen.findByRole("tab", { name: "Metrics", selected: true })).toBeInTheDocument();
  });

  it("preserves subscription isolation in unused API payload", async () => {
    await renderUnusedWorkspace({
      subscriptions: [
        { id: "sub-db-1", name: "GNX-SERVICE-DEV", subscription_id: "sub-ext-1" },
        { id: "sub-db-2", name: "GNX-SERVICE-PROD", subscription_id: "sub-ext-2" },
      ],
    });

    const before = api.getUnusedResourceSummary.mock.calls.length;

    fireEvent.change(screen.getByLabelText("Monitoring subscription"), { target: { value: "sub-ext-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Refresh Monitoring" }));
    await waitFor(() => {
      expect(screen.getAllByText("GNX-SERVICE-PROD (sub-ext-2)").length).toBeGreaterThan(0);
      expect(api.getUnusedResourceSummary.mock.calls.length).toBeGreaterThan(before);
    });
  });

  it("shows unavailable instead of fabricated values when estimate is missing", async () => {
    await renderUnusedWorkspace({
      unusedPayload: baseUnusedPayload({ estimated_monthly_waste: null }),
    });
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
  });
});
