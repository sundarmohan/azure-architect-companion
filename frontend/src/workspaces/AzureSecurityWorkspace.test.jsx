import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AzureSecurityWorkspace, { correlateThreatEvidence } from "./AzureSecurityWorkspace";

it("correlates exact resource identities across Defender and Activity signals", () => {
  const resource = "/subscriptions/sub-a/resourceGroups/example/providers/Microsoft.Compute/virtualMachines/vm";
  const alert = { resource_id: resource, source: "azure_defender_alerts", code: "defender_active_alerts" };
  const activity = { resource_id: resource.toUpperCase(), source: "azure_activity_rule", code: "repeated_security_control_failures" };
  expect(correlateThreatEvidence([
    alert, activity, { ...alert, resource_id: "/subscriptions/sub-a" },
    { ...activity, resource_id: "/subscriptions/sub-a" },
    { ...activity, resource_id: resource.replace("sub-a", "sub-b") },
    { ...activity, resource_id: resource + "/extensions/extra" },
    { ...activity, code: "azure_security_control_activity" },
  ], "sub-a")).toEqual([{ resource, alerts: [alert], activity: [activity] }]);
});
import { getAzureConnectionStatus, getAzureSecurity, refreshAzureSecurity, updateAzureFindingTracking } from "../services/api";

vi.mock("../services/api", () => ({
  getAzureConnectionStatus: vi.fn(),
  getAzureSecurity: vi.fn(),
  refreshAzureSecurity: vi.fn(),
  updateAzureFindingTracking: vi.fn(),
}));

const SUBSCRIPTION = "subscription-a";
const FINDING_ID = "a".repeat(64);
const snapshot = {
  status: "synced",
  last_success_at: "2026-11-01T00:00:00Z",
  score: 41,
  score_factors: [{ severity: "high", count: 1, weight: 25 }, { severity: "medium", count: 1, weight: 16 }],
  limitations: ["Security alerts depend on Microsoft Defender for Cloud coverage."],
  findings: [
    {
      code: "NSG_INBOUND_ANY",
      title: "Broad inbound NSG rule",
      severity: "high",
      source: "network_configuration",
      category: "network",
      resource_id: "/azure/security-groups/one",
      evidence: ["Azure reported a broad inbound source range."],
      recommendation: "Review the allowed source ranges.",
    },
    {
      code: "DEFENDER_ALERT",
      title: "Defender alert",
      severity: "medium",
      source: "defender",
      category: "threat",
      resource_id: "/azure/resources/two",
      evidence: ["Microsoft Defender for Cloud reported one active alert."],
    },
  ],
};

beforeEach(() => {
  vi.resetAllMocks();
  getAzureConnectionStatus.mockResolvedValue({ configured_subscription_id: SUBSCRIPTION, configured_subscription_ids: [SUBSCRIPTION] });
});

describe("Azure Security workspace", () => {
  it("shows score, source evidence, and limitations and filters findings by category", async () => {
    getAzureSecurity.mockResolvedValue(snapshot);
    render(<AzureSecurityWorkspace canRefresh />);

    expect(await screen.findByText("41 / 100")).toBeInTheDocument();
    expect(screen.getByText(snapshot.limitations[0])).toBeInTheDocument();
    expect(screen.getByText("Azure reported a broad inbound source range.")).toBeInTheDocument();
    expect(screen.getByText("Review the allowed source ranges.")).toBeInTheDocument();
    expect(screen.getByText("Score factors")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Category"), { target: { value: "threat" } });
    expect(screen.queryByText("Broad inbound NSG rule")).not.toBeInTheDocument();
    expect(screen.getByText("Defender alert")).toBeInTheDocument();
    expect(getAzureSecurity).toHaveBeenCalledWith(SUBSCRIPTION);
  });

  it("lets viewers reload the saved snapshot and distinguishes an unavailable score from zero", async () => {
    getAzureSecurity.mockResolvedValueOnce({ status: "not_synced", score: null, findings: [] })
      .mockResolvedValueOnce({ status: "synced", score: 0, findings: [] });
    render(<AzureSecurityWorkspace canRefresh={false} />);

    expect(await screen.findByText("Unavailable")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Refresh snapshot" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reload saved snapshot" }));
    expect(await screen.findByText("0 / 100")).toBeInTheDocument();
    expect(refreshAzureSecurity).not.toHaveBeenCalled();
  });

  it("allows operators to refresh scoped security evidence and shows an incomplete result", async () => {
    getAzureSecurity.mockResolvedValue(snapshot);
    refreshAzureSecurity.mockResolvedValue({ ...snapshot, status: "partial_failure" });
    render(<AzureSecurityWorkspace canRefresh />);

    await screen.findByText("41 / 100");
    fireEvent.click(screen.getByRole("button", { name: "Refresh snapshot" }));
    expect(await screen.findByText("Some Azure data could not be collected.")).toBeInTheDocument();
    expect(screen.getByText("Showing the last available data.")).toBeInTheDocument();
    expect(screen.getByText("Triage is based on retained findings from the last complete collection.")).toBeInTheDocument();
    expect(screen.getByText("Broad inbound NSG rule")).toBeInTheDocument();
    await waitFor(() => expect(refreshAzureSecurity).toHaveBeenCalledWith(SUBSCRIPTION));
  });

  it("shows saved tracking to viewers without edit fields", async () => {
    getAzureSecurity.mockResolvedValue({
      ...snapshot,
      findings: [{ ...snapshot.findings[0], id: FINDING_ID, tracking: {
        status: "accepted", owner: "Cloud operations", due_date: "2026-11-30",
      } }],
    });
    render(<AzureSecurityWorkspace canRefresh={false} />);

    const summary = await screen.findByText("Remediation tracking · Accepted");
    fireEvent.click(summary);
    expect(screen.getByText("Cloud operations")).toBeInTheDocument();
    expect(screen.getByText("2026-11-30")).toBeInTheDocument();
    expect(screen.queryByLabelText("Status")).not.toBeInTheDocument();
    expect(updateAzureFindingTracking).not.toHaveBeenCalled();
  });

  it("saves remediation status, owner, and due date with the finding and subscription IDs", async () => {
    getAzureSecurity.mockResolvedValue({
      ...snapshot,
      findings: [{ ...snapshot.findings[0], id: FINDING_ID, tracking: null }],
    });
    updateAzureFindingTracking.mockResolvedValue({
      status: "in_progress", owner: "Security operations", due_date: "2026-11-30",
    });
    render(<AzureSecurityWorkspace canRefresh />);

    fireEvent.click(await screen.findByText("Remediation tracking · Open"));
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "in_progress" } });
    fireEvent.change(screen.getByLabelText("Owner"), { target: { value: " Security operations " } });
    fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2026-11-30" } });
    fireEvent.click(screen.getByRole("button", { name: "Save tracking" }));

    expect(await screen.findByText("Remediation tracking saved.")).toBeInTheDocument();
    expect(screen.getByText("Remediation tracking · In progress")).toBeInTheDocument();
    expect(updateAzureFindingTracking).toHaveBeenCalledWith(SUBSCRIPTION, FINDING_ID, {
      status: "in_progress", owner: "Security operations", due_date: "2026-11-30",
    });
  });

  it("triages overdue and unassigned work and updates the open queue after a save", async () => {
    const [rule, alert] = snapshot.findings;
    getAzureSecurity.mockResolvedValue({
      ...snapshot,
      status: "partial_failure",
      last_success_at: null,
      findings: [
        { ...rule, id: FINDING_ID },
        { ...alert, id: "b".repeat(64), tracking: {
          status: "in_progress", owner: "Operations", due_date: "2000-01-01",
        } },
        { ...alert, title: "Previously resolved alert", id: "c".repeat(64), tracking: {
          status: "resolved", owner: null, due_date: "2000-01-01",
        } },
      ],
    });
    updateAzureFindingTracking.mockResolvedValue({ status: "resolved", owner: "Operations", due_date: null });
    render(<AzureSecurityWorkspace canRefresh />);

    expect(await screen.findByText("Triage is based on incomplete Azure evidence.")).toBeInTheDocument();
    expect(screen.getByText("Outstanding 2 · Overdue 1 · Unassigned 1")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Needs attention"), { target: { value: "overdue" } });
    expect(screen.getByText("Defender alert")).toBeInTheDocument();
    expect(screen.queryByText("Previously resolved alert")).not.toBeInTheDocument();
    expect(screen.queryByText(rule.title)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Needs attention"), { target: { value: "unassigned" } });
    expect(screen.getByText(rule.title)).toBeInTheDocument();
    expect(screen.queryByText("Defender alert")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Needs attention"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Tracking status"), { target: { value: "open" } });
    fireEvent.click(screen.getByText("Remediation tracking · Open"));
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "resolved" } });
    fireEvent.click(screen.getByRole("button", { name: "Save tracking" }));
    expect(await screen.findByText("No findings match the filters.")).toBeInTheDocument();
    expect(screen.getByText("Remediation tracking saved.")).toBeInTheDocument();
    expect(screen.getByText("Outstanding 1 · Overdue 1 · Unassigned 0")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Tracking status"), { target: { value: "resolved" } });
    expect(screen.getByText(rule.title)).toBeInTheDocument();
    expect(screen.getByText("Previously resolved alert")).toBeInTheDocument();
  });
});
