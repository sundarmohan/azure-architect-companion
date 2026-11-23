import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AzureMonitoringWorkspace from "./AzureMonitoringWorkspace";
import {
  acknowledgeAzureHealthAlert,
  createAzureHealthIncident,
  getAzureConnectionStatus,
  getAzureHealthIncidents,
  getAzureIncidentAttention,
  getAzureInventory,
  getAzureMonitoring,
  getAzureMetricThreshold,
  getAzureMonitoringSchedule,
  queryAzureDiagnostics,
  refreshAzureMonitoring,
  updateAzureMonitoringSchedule,
  updateAzureHealthIncident,
} from "../services/api";

vi.mock("../services/api", () => ({
  acknowledgeAzureHealthAlert: vi.fn(),
  createAzureHealthIncident: vi.fn(),
  getAzureConnectionStatus: vi.fn(),
  getAzureHealthIncidents: vi.fn(),
  getAzureIncidentAttention: vi.fn(),
  getAzureInventory: vi.fn(),
  getAzureMonitoring: vi.fn(),
  getAzureMetricThreshold: vi.fn(),
  refreshAzureMonitoring: vi.fn(),
  getAzureMonitoringSchedule: vi.fn(),
  queryAzureDiagnostics: vi.fn(),
  updateAzureMonitoringSchedule: vi.fn(),
  updateAzureHealthIncident: vi.fn(),
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
      health_status: "synced",
      metrics_status: "available",
      metrics: [{ name: "Percentage CPU", unit: "Percent", points: [{ timestamp: "2026-11-01T00:00:00Z", value: 0 }] }],
    }],
    ...extra,
  };
}

beforeEach(() => {
  vi.resetAllMocks();
  getAzureConnectionStatus.mockResolvedValue({ configured_subscription_id: SUBSCRIPTIONS[0], configured_subscription_ids: SUBSCRIPTIONS });
  getAzureMetricThreshold.mockResolvedValue({
    threshold: null, assessment: null, choices: [], snapshot_status: "not_synced",
    last_attempt_at: null, last_success_at: null,
  });
  getAzureIncidentAttention.mockResolvedValue({ unassigned_incidents: [], overdue_actions: [] });
});

describe("Azure monitoring workspace", () => {
  it("triages only confirmed Azure health issues and opens the matching resource", async () => {
    getAzureMonitoring.mockResolvedValue(snapshot("vm-available", {
      resources: [
        { id: "a", name: "vm-available", health_status: "synced", health: "available" },
        { id: "b", name: "vm-degraded", health_status: "synced", health: "degraded" },
        { id: "c", name: "vm-unavailable", health_status: "synced", health: "unavailable" },
        { id: "d", name: "vm-unknown", health_status: "synced", health: "unknown" },
        { id: "e", name: "vm-unconfirmed", health_status: "permission_failure", health: "degraded" },
      ],
    }));
    render(<AzureMonitoringWorkspace />);

    const triage = within(await screen.findByRole("table", { name: "Confirmed Azure resource health issues" }));
    expect(triage.getByRole("button", { name: "Review vm-degraded" })).toBeInTheDocument();
    expect(triage.queryByRole("button", { name: "Review vm-available" })).not.toBeInTheDocument();
    expect(triage.queryByRole("button", { name: "Review vm-unknown" })).not.toBeInTheDocument();
    expect(triage.queryByRole("button", { name: "Review vm-unconfirmed" })).not.toBeInTheDocument();
    expect(screen.getByText(/confirmed the state of 3 of 5 sampled resources/)).toBeInTheDocument();

    const filter = screen.getByLabelText("Filter monitored resources");
    fireEvent.change(filter, { target: { value: "vm-available" } });
    fireEvent.click(triage.getByRole("button", { name: "Review vm-unavailable" }));
    expect(filter).toHaveValue("");
    expect(screen.getByRole("heading", { name: /Resource health and metrics/ })).toHaveFocus();
    expect(screen.getByRole("heading", { name: "vm-unavailable" })).toBeInTheDocument();
  });

  it("shows acknowledgement to viewers and lets an editor acknowledge exact saved evidence", async () => {
    const health_alert = { evidence_id: "a".repeat(64), acknowledged_at: null };
    getAzureMonitoring.mockResolvedValue(snapshot("vm", {
      resources: [{ id: "vm", name: "vm", health_status: "synced", health: "degraded", health_alert }],
    }));
    acknowledgeAzureHealthAlert.mockResolvedValue({ ...health_alert, acknowledged_at: "2026-11-01T01:00:00Z" });
    const { rerender } = render(<AzureMonitoringWorkspace />);

    expect(await screen.findByText("Pending acknowledgement")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Acknowledge vm" })).not.toBeInTheDocument();

    rerender(<AzureMonitoringWorkspace canRefresh />);
    fireEvent.click(screen.getByRole("button", { name: "Acknowledge vm" }));
    expect(await screen.findByText(/^Acknowledged /)).toBeInTheDocument();
    expect(acknowledgeAzureHealthAlert).toHaveBeenCalledWith(SUBSCRIPTIONS[0], health_alert.evidence_id);
  });

  it("opens a human-created incident for acknowledged evidence and saves investigation details", async () => {
    const timestamp = "2026-11-01T01:00:00Z";
    const incident = { id: "incident", evidence_id: "a".repeat(64), resource_id: "vm-id", status: "open",
      collected_at: timestamp, acknowledged_at: timestamp, updated_at: timestamp, health: "degraded" };
    const health_alert = { evidence_id: incident.evidence_id, acknowledged_at: timestamp };
    getAzureMonitoring.mockResolvedValue(snapshot("vm", {
      resources: [{ id: "vm-id", name: "vm", health_status: "synced", health: "degraded", health_alert }],
    }));
    createAzureHealthIncident.mockResolvedValue(incident);
    getAzureHealthIncidents.mockResolvedValue({ incidents: [], has_next: false });
    updateAzureHealthIncident.mockResolvedValue({ ...incident, status: "investigating", owner: "Operations",
      rca_note: "Reviewing evidence", updated_at: "2026-11-01T01:01:00Z" });
    render(<AzureMonitoringWorkspace canRefresh />);

    fireEvent.click(await screen.findByRole("button", { name: "Create or open incident for vm" }));
    expect(await screen.findByText("Incident recorded for the acknowledged evidence.")).toBeInTheDocument();
    expect(createAzureHealthIncident).toHaveBeenCalledWith(SUBSCRIPTIONS[0], incident.evidence_id);
    expect(await screen.findByText("vm-id · Open")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Incident status"), { target: { value: "investigating" } });
    fireEvent.change(screen.getByLabelText("Incident owner"), { target: { value: "Operations" } });
    fireEvent.change(screen.getByLabelText("Investigation and RCA note"), { target: { value: "Reviewing evidence" } });
    fireEvent.click(screen.getByRole("button", { name: "Save incident" }));
    expect(await screen.findByText("Incident updated.")).toBeInTheDocument();
    expect(updateAzureHealthIncident).toHaveBeenCalledWith(SUBSCRIPTIONS[0], incident.id, {
      status: "investigating", owner: "Operations", rca_note: "Reviewing evidence", updated_at: timestamp,
    });
  });

  it("distinguishes retained, incomplete, and unconfirmed evidence", async () => {
    const issues = [{ id: "vm", name: "vm", health_status: "synced", health: "degraded" }];
    getAzureMonitoring.mockResolvedValue(snapshot("vm", {
      status: "partial_failure",
      last_attempt_at: "2026-11-01T02:00:00Z",
      resources: issues,
    }));
    refreshAzureMonitoring.mockResolvedValueOnce(snapshot("vm", {
      status: "partial_failure",
      last_success_at: null,
      last_attempt_at: "2026-11-01T03:00:00Z",
      resources: issues,
    })).mockResolvedValueOnce(snapshot("vm", {
      resources: [{ ...issues[0], health: "unknown" }],
    }));
    render(<AzureMonitoringWorkspace canRefresh />);

    expect(await screen.findByText(/Retained evidence from/)).toHaveTextContent(/latest collection did not complete/);
    expect(screen.getByRole("button", { name: "Review vm" })).toBeInTheDocument();
    const refresh = screen.getByRole("button", { name: "Refresh snapshot" });
    fireEvent.click(refresh);
    expect(await screen.findByText(/Incomplete evidence from the collection attempted at/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review vm" })).toBeInTheDocument();
    fireEvent.click(refresh);
    expect(await screen.findByText("No confirmed resource health evidence is available.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review vm" })).not.toBeInTheDocument();
  });

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
    expect(screen.queryByRole("button", { name: "Open advanced diagnostics" })).not.toBeInTheDocument();
    expect(getAzureMonitoringSchedule).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Reload saved snapshot" }));
    await waitFor(() => expect(getAzureMonitoring).toHaveBeenCalledTimes(2));
    expect(refreshAzureMonitoring).not.toHaveBeenCalled();
  });

  it("saves the collection schedule for the selected subscription as an administrator", async () => {
    getAzureMonitoring.mockResolvedValue(snapshot("vm-a"));
    getAzureMonitoringSchedule.mockResolvedValue({ enabled: false, interval_minutes: 60, next_run_at: null });
    updateAzureMonitoringSchedule.mockResolvedValue({
      enabled: true, interval_minutes: 30, include_security: true, next_run_at: "2026-11-01T01:00:00Z",
    });
    render(<AzureMonitoringWorkspace canRefresh canManageSchedule />);

    fireEvent.click(await screen.findByLabelText("Enable scheduled collection"));
    const includeSecurity = screen.getByLabelText("Include security posture and threats");
    expect(includeSecurity).not.toBeChecked();
    fireEvent.click(includeSecurity);
    fireEvent.change(screen.getByLabelText("Interval (minutes)"), { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "Save schedule" }));

    expect(await screen.findByText("Schedule saved.")).toBeInTheDocument();
    expect(updateAzureMonitoringSchedule).toHaveBeenCalledWith(SUBSCRIPTIONS[0], {
      enabled: true, interval_minutes: 30, include_security: true,
    });
  });

  it("queries bounded aggregates for an inventory resource as an operator", async () => {
    getAzureMonitoring.mockResolvedValue(snapshot("vm-a"));
    getAzureInventory.mockResolvedValue({
      resources: [{ id: "/azure-resource-a", name: "VM A", type: "Microsoft.Compute/virtualMachines", resource_group: "ops" }],
    });
    queryAzureDiagnostics.mockResolvedValue({
      status: "partial_failure",
      source: "guest",
      hours: 6,
      rows: [{ timestamp: "2026-11-01T00:00:00Z", category: "Linux syslog", count: 3 }],
    });
    render(<AzureMonitoringWorkspace canRefresh />);
    fireEvent.click(await screen.findByRole("button", { name: "Open advanced diagnostics" }));
    fireEvent.change(await screen.findByLabelText("Diagnostic resource"), { target: { value: "/azure-resource-a" } });
    fireEvent.change(screen.getByLabelText("Log source"), { target: { value: "guest" } });
    fireEvent.change(screen.getByLabelText("Time range"), { target: { value: "6" } });
    fireEvent.click(screen.getByRole("button", { name: "Query diagnostics" }));

    expect(await screen.findByText(/Counts may be partial/)).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Linux syslog" })).toBeInTheDocument();
    expect(getAzureInventory).toHaveBeenCalledWith(SUBSCRIPTIONS[0]);
    expect(queryAzureDiagnostics).toHaveBeenCalledWith(SUBSCRIPTIONS[0], {
      resource_id: "/azure-resource-a", source: "guest", hours: 6,
    });
  });
});
