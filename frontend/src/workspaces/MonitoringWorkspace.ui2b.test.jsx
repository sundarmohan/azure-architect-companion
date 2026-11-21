import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import MonitoringWorkspace, {
  classifyFindingType,
  confidenceExplanation,
  parseIdleSignalEvidence,
} from "./MonitoringWorkspace";

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

function summaryPayload() {
  return {
    state: "live",
    total_resources: 2,
    monitored_resources: 2,
    live_resources: 2,
    healthy_count: 1,
    warning_count: 1,
    critical_count: 0,
    no_data_count: 0,
    unsupported_count: 0,
    error_count: 0,
    resources: [
      {
        architecture_id: "arch-1",
        resource_id: "res-vm",
        resource_name: "VM-Prod-01",
        resource_type: "vm",
        state: "live",
        live: true,
        health_status: "Available",
        metrics: [
          {
            name: "Percentage CPU",
            unit: "Percent",
            aggregation: "average",
            points: [
              { timestamp: "2026-08-31T00:00:00Z", value: 30 },
              { timestamp: "2026-08-31T01:00:00Z", value: 42 },
            ],
          },
          {
            name: "Network In Total",
            unit: "Bytes",
            aggregation: "total",
            points: [{ timestamp: "2026-08-31T01:00:00Z", value: 1024 }],
          },
        ],
      },
      {
        architecture_id: "arch-1",
        resource_id: "res-app",
        resource_name: "App-01",
        resource_type: "appservice",
        state: "no_data",
        live: false,
        health_status: null,
        metrics: [],
        message: "No Azure Monitor data available in selected time range",
      },
    ],
  };
}

function resourceMonitoringPayload() {
  return {
    architecture_id: "arch-1",
    resource_id: "res-vm",
    resource_name: "VM-Prod-01",
    resource_type: "vm",
    state: "live",
    source: "azure_monitor",
    live: true,
    health_status: "Available",
    metrics: [
      {
        name: "Percentage CPU",
        unit: "Percent",
        aggregation: "average",
        points: [
          { timestamp: "2026-08-31T00:00:00Z", value: 30 },
          { timestamp: "2026-08-31T01:00:00Z", value: 42 },
          { timestamp: "2026-08-31T02:00:00Z", value: 38 },
        ],
      },
      {
        name: "Network In Total",
        unit: "Bytes",
        aggregation: "total",
        points: [
          { timestamp: "2026-08-31T00:00:00Z", value: 300 },
          { timestamp: "2026-08-31T01:00:00Z", value: 900 },
        ],
      },
    ],
  };
}

function unusedPayload() {
  return {
    architecture_id: "arch-1",
    source: "legacy_idle_detector",
    state: "evaluated",
    lookback_days: 7,
    analysis_start_time: "2026-08-24T00:00:00Z",
    analysis_end_time: "2026-08-31T00:00:00Z",
    total_checked: 2,
    total_unused: 1,
    estimated_monthly_waste: 12.5,
    azure_connection_state: "configured",
    azure_connection_message: "ok",
    message: "Unused resource analysis completed.",
    unused_resources: [
      {
        resource_id: "res-app",
        resource_name: "App-01",
        resource_type: "microsoft.web/sites",
        location: "eastus",
        resource_group: "rg-app",
        subscription_id: "sub-ext-1",
        idle_reason: "Requests below threshold",
        idle_signals: ["requests_below_10(total=2.0)"],
        confidence: "high",
        recommended_action: "Review and right-size",
        days_checked: 7,
        monthly_cost_estimate: 12.5,
        portal_link: "https://portal.azure.com/#resource/abc",
      },
    ],
  };
}

async function renderWorkspace() {
  api.listArchitectures.mockResolvedValue([{ id: "arch-1", name: "Arch One" }]);
  api.getSettingsOverview.mockResolvedValue({ azure_integration: { connection_state: "configured" } });
  api.listSubscriptions.mockResolvedValue([{ id: "sub-db-1", name: "GNX-SERVICE-DEV", subscription_id: "sub-ext-1" }]);
  api.listResources.mockResolvedValue([
    {
      id: "res-vm",
      name: "VM-Prod-01",
      resource_type: "vm",
      resource_group_id: "rg-1",
      properties: {
        azure_resource_id: "/subscriptions/sub-ext-1/resourceGroups/rg-vm/providers/Microsoft.Compute/virtualMachines/vm1",
        azure_subscription_id: "sub-ext-1",
      },
    },
    {
      id: "res-app",
      name: "App-01",
      resource_type: "appservice",
      resource_group_id: "rg-2",
      properties: {
        azure_resource_id: "/subscriptions/sub-ext-1/resourceGroups/rg-app/providers/Microsoft.Web/sites/app1",
        azure_subscription_id: "sub-ext-1",
      },
    },
  ]);
  api.listResourceGroups.mockResolvedValue([
    { id: "rg-1", name: "rg-vm" },
    { id: "rg-2", name: "rg-app" },
  ]);
  api.getArchitectureMonitoringSummary.mockResolvedValue(summaryPayload());
  api.getResourceMonitoring.mockResolvedValue(resourceMonitoringPayload());
  api.getMonitoringIncidentSummary.mockResolvedValue({ incident_count: 0, incidents: [], critical_count: 0, high_count: 0, medium_count: 0, low_count: 0 });
  api.getMonitoringAlertSummary.mockResolvedValue({ alert_count: 0, alerts: [], critical_count: 0, high_count: 0, medium_count: 0, low_count: 0, open_count: 0, acknowledged_count: 0, resolved_count: 0 });
  api.listMonitoringIncidents.mockResolvedValue([]);
  api.getMonitoringIncidentDetail.mockResolvedValue(null);
  api.updateMonitoringIncidentStatus.mockResolvedValue(null);
  api.getUnusedResourceSummary.mockResolvedValue(unusedPayload());

  render(<MonitoringWorkspace />);

  await waitFor(() => expect(api.getArchitectureMonitoringSummary).toHaveBeenCalled());
  await waitFor(() => expect(screen.getByRole("tab", { name: "Resources" })).toBeInTheDocument());
}

describe("Monitoring Workspace UI-2B", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("classifies finding types and parses signal evidence", () => {
    expect(classifyFindingType({ idle_signals: ["config_unattached"] })).toBe("unused");
    expect(classifyFindingType({ idle_signals: ["cpu_avg_below_5pct(average=2.1)"] })).toBe("low_utilization");
    expect(confidenceExplanation("high")).toContain("Strong evidence");

    const parsed = parseIdleSignalEvidence("cpu_avg_below_5pct(average=2.1)");
    expect(parsed).toBeTruthy();
    expect(parsed.observed).toBe(2.1);
    expect(parsed.threshold).toContain("< 5%");
  });

  it("renders resource operations table with CPU/memory/disk/network columns and capability-aware values", async () => {
    await renderWorkspace();

    fireEvent.click(screen.getByRole("tab", { name: "Resources" }));

    expect(await screen.findByText("Resource Operations")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "CPU" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Memory/RAM" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disk" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Network" })).toBeInTheDocument();

    expect(screen.getAllByText("VM-Prod-01").length).toBeGreaterThan(0);

    const vmRow = screen.getAllByText("VM-Prod-01").find((node) => node.closest("tr"))?.closest("tr");
    expect(vmRow).toBeTruthy();
    expect(within(vmRow).getByLabelText("CPU current value").textContent).toContain("42");

    const appRow = screen.getByText("App-01").closest("tr");
    expect(appRow).toBeTruthy();
    expect(within(appRow).getAllByText("Not available").length).toBeGreaterThan(0);
  });

  it("supports time-range switching and passes monitoring window to APIs", async () => {
    await renderWorkspace();

    const timeRange = screen.getByLabelText("Monitoring time range");
    fireEvent.change(timeRange, { target: { value: "1h" } });

    await waitFor(() => {
      const summaryCall = api.getArchitectureMonitoringSummary.mock.calls.find((call) => call?.[1]?.interval === "PT5M");
      expect(summaryCall).toBeTruthy();
      expect(summaryCall?.[1]?.start_time).toBeTruthy();
      expect(summaryCall?.[1]?.end_time).toBeTruthy();
    });
  });

  it("shows resource drill-down with KPI cards, trends, and statistics from real points", async () => {
    await renderWorkspace();

    fireEvent.click(screen.getByRole("tab", { name: "Resources" }));
    const vmCell = (await screen.findAllByText("VM-Prod-01")).find((node) => node.closest("tr"));
    expect(vmCell).toBeTruthy();
    fireEvent.click(vmCell);

    expect(await screen.findByLabelText("Resource monitoring detail")).toBeInTheDocument();
    expect(screen.getByText("CPU Trend")).toBeInTheDocument();
    expect(screen.getByText("Memory / RAM Trend")).toBeInTheDocument();
    expect(screen.getByText("Disk Trend")).toBeInTheDocument();
    expect(screen.getByText("Network Trend")).toBeInTheDocument();
    expect(screen.getByText("Statistics")).toBeInTheDocument();
    expect(screen.getByText("Percentage CPU")).toBeInTheDocument();
  });

  it("renders overview attention and allows navigation to related tabs", async () => {
    await renderWorkspace();

    expect(await screen.findByText("Needs Attention")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /High\/Critical alerts/i }));
    await waitFor(() => expect(screen.getByRole("tab", { name: "Alerts" }).getAttribute("aria-selected")).toBe("true"));
  });

  it("shows clear empty state when no resources in selected scope", async () => {
    api.listArchitectures.mockResolvedValue([{ id: "arch-1", name: "Arch One" }]);
    api.getSettingsOverview.mockResolvedValue({ azure_integration: { connection_state: "configured" } });
    api.listSubscriptions.mockResolvedValue([{ id: "sub-db-1", name: "GNX-SERVICE-DEV", subscription_id: "sub-ext-1" }]);
    api.listResources.mockResolvedValue([]);
    api.listResourceGroups.mockResolvedValue([]);
    api.getArchitectureMonitoringSummary.mockResolvedValue({
      state: "no_data",
      total_resources: 0,
      monitored_resources: 0,
      live_resources: 0,
      healthy_count: 0,
      warning_count: 0,
      critical_count: 0,
      no_data_count: 0,
      unsupported_count: 0,
      error_count: 0,
      resources: [],
    });
    api.getResourceMonitoring.mockResolvedValue({ state: "no_data", metrics: [], health_status: null });
    api.getMonitoringIncidentSummary.mockResolvedValue({ incident_count: 0, incidents: [], critical_count: 0, high_count: 0, medium_count: 0, low_count: 0 });
    api.getMonitoringAlertSummary.mockResolvedValue({ alert_count: 0, alerts: [], critical_count: 0, high_count: 0, medium_count: 0, low_count: 0, open_count: 0, acknowledged_count: 0, resolved_count: 0 });
    api.listMonitoringIncidents.mockResolvedValue([]);
    api.getMonitoringIncidentDetail.mockResolvedValue(null);
    api.updateMonitoringIncidentStatus.mockResolvedValue(null);
    api.getUnusedResourceSummary.mockResolvedValue(unusedPayload());

    render(<MonitoringWorkspace />);
    await waitFor(() => expect(api.getArchitectureMonitoringSummary).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("tab", { name: "Resources" }));
    expect(await screen.findByText(/No resources found for this subscription/i)).toBeInTheDocument();
  });

  it("preserves subscription scope in monitoring API payloads", async () => {
    await renderWorkspace();

    await waitFor(() => {
      const hasScopedCall = api.getArchitectureMonitoringSummary.mock.calls.some((call) => call?.[1]?.subscription_id === "sub-ext-1");
      expect(hasScopedCall).toBe(true);
    });
  });
});
