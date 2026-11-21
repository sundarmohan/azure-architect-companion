import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AzureSecurityWorkspace from "./AzureSecurityWorkspace";
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
});
