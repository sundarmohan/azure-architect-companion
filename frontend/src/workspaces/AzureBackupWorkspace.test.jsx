import { expect, it } from "vitest";
import { compareRecoveryEvidence } from "./AzureBackupWorkspace";

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
