import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { getAzureBackupEvidence, getAzureConnectionStatus, getAzureRecoveryObjectives, getAzureRestoreTests,
  saveAzureRecoveryObjectives } from "../services/api";
import AzureBackupWorkspace, { compareRecoveryEvidence } from "./AzureBackupWorkspace";

vi.mock("../services/api", () => ({
  getAzureBackupEvidence: vi.fn(),
  getAzureConnectionStatus: vi.fn(),
  getAzureRecoveryObjectives: vi.fn(),
  getAzureRestoreTests: vi.fn(),
  recordAzureRestoreTest: vi.fn(),
  saveAzureRecoveryObjectives: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  getAzureConnectionStatus.mockResolvedValue({ configured_subscription_ids: ["sub-a", "sub-b"] });
  getAzureBackupEvidence.mockResolvedValue({ status: "no_vaults_in_inventory", vaults: [] });
  getAzureRestoreTests.mockResolvedValue([]);
});

it("compares only captured recovery point times and completed restore job durations", () => {
  const reference = "2026-11-23T12:00:00Z";
  const vault = {
    protected_items: { rows: [
      { lastRecoveryPoint: "2026-11-23T11:00:00Z" },
      { lastRecoveryPoint: "2026-11-22T12:00:00Z" },
      { lastRecoveryPoint: "2026-11-24T12:00:00Z" },
      {},
    ] },
    jobs: { rows: [
      { operation: "Restore", status: "Completed", startTime: "2026-11-23T09:00:00Z", endTime: "2026-11-23T11:00:00Z" },
      { operation: "Restore", status: "Failed", startTime: "2026-11-23T09:00:00Z", endTime: "2026-11-23T11:00:00Z" },
      { operation: "Backup", status: "Completed", startTime: "2026-11-23T09:00:00Z", endTime: "2026-11-23T11:00:00Z" },
    ] },
  };
  expect(compareRecoveryEvidence(vault, reference, 2, 60)).toEqual({
    recoveryPoints: 2, pointsOutside: 1, restoreJobs: 1, restoresOutside: 1,
  });
});

it("loads and saves objectives for the chosen subscription even without vault evidence", async () => {
  getAzureRecoveryObjectives.mockResolvedValueOnce({ rpo_hours: 24, rto_minutes: 60 }).mockResolvedValueOnce(null);
  saveAzureRecoveryObjectives.mockResolvedValue({ rpo_hours: 24, rto_minutes: 90 });
  render(<AzureBackupWorkspace canEdit />);

  expect(await screen.findByText(/Saved targets for this subscription: 24 hours RPO and 60 minutes RTO/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Recovery time objective (minutes)"), { target: { value: "90" } });
  fireEvent.click(screen.getByRole("button", { name: "Save recovery objectives" }));
  expect(await screen.findByText("Recovery objectives saved.")).toBeInTheDocument();
  expect(saveAzureRecoveryObjectives).toHaveBeenCalledWith("sub-a", { rpo_hours: 24, rto_minutes: 90 });
  fireEvent.change(screen.getByLabelText("Subscription"), { target: { value: "sub-b" } });
  expect(await screen.findByText("No recovery objectives are saved for this subscription.")).toBeInTheDocument();
  expect(screen.queryByText(/24 hours RPO/)).not.toBeInTheDocument();
});

it("lets viewers compare temporary targets while keeping stored objectives read-only", async () => {
  getAzureRecoveryObjectives.mockResolvedValue({ rpo_hours: 24, rto_minutes: 60 });
  render(<AzureBackupWorkspace />);
  expect(await screen.findByText(/Saved targets for this subscription/)).toBeInTheDocument();
  const input = screen.getByLabelText("Recovery point objective (hours)");
  fireEvent.change(input, { target: { value: "12" } });
  expect(input).toHaveValue(12);
  expect(screen.queryByRole("button", { name: "Save recovery objectives" })).not.toBeInTheDocument();
  expect(saveAzureRecoveryObjectives).not.toHaveBeenCalled();
});

it("shows reported Site Recovery replication evidence with its coverage limit", async () => {
  const empty = { status: "synced", rows: [] };
  getAzureRecoveryObjectives.mockResolvedValue(null);
  getAzureBackupEvidence.mockResolvedValue({
    status: "synced",
    vaults: [{
      id: "vault-a", name: "Recovery vault A", jobs: empty, protected_items: empty, policies: empty,
      replication_items: { status: "synced", truncated: true, rows: [
        { friendlyName: "Replicated VM", protectionState: "Protected", replicationHealth: "Normal",
          lastRecoveryPointReceived: "2026-11-23T10:00:00Z" },
        { friendlyName: "Another VM" },
      ] },
    }],
  });
  render(<AzureBackupWorkspace />);
  const evidence = within(await screen.findByRole("table", { name: "Site Recovery replication" }));
  expect(evidence.getByText("Normal")).toBeInTheDocument();
  expect(evidence.getByText("2026-11-23T10:00:00Z")).toBeInTheDocument();
  expect(evidence.getAllByText("Unavailable")).toHaveLength(3);
  expect(screen.getByText("Synced | First page only")).toBeInTheDocument();
});
