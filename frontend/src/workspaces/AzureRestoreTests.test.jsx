import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import AzureRestoreTests from "./AzureRestoreTests";
import { getAzureRestoreTests, recordAzureRestoreTest } from "../services/api";

vi.mock("../services/api", () => ({ getAzureRestoreTests: vi.fn(), recordAzureRestoreTest: vi.fn() }));

beforeEach(() => {
  vi.resetAllMocks();
  getAzureRestoreTests.mockResolvedValue([]);
});

it("records append-only restore exercise evidence", async () => {
  recordAzureRestoreTest.mockImplementation(async (_subscription, id, data) => ({
    id, ...data, created_at: "2026-11-23T12:00:00Z",
  }));
  render(<AzureRestoreTests subscription="sub-a" canEdit />);
  expect(await screen.findByText("No restore tests are recorded for this subscription.")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Record restore test", { selector: "summary" }));
  fireEvent.change(screen.getByLabelText("Restored resource or workload"), { target: { value: "Finance VM" } });
  fireEvent.change(screen.getByLabelText("Test completed at"), { target: { value: "2026-11-01T10:00" } });
  fireEvent.change(screen.getByLabelText("Observed recovery time (minutes)"), { target: { value: "45" } });
  fireEvent.change(screen.getByLabelText("Evidence reference"), { target: { value: "change-1042" } });
  fireEvent.click(screen.getByRole("button", { name: "Record restore test" }));

  await waitFor(() => expect(recordAzureRestoreTest).toHaveBeenCalledWith("sub-a", expect.any(String), {
    resource_name: "Finance VM", tested_at: "2026-11-01T10:00:00.000Z", outcome: "passed",
    recovery_minutes: 45, evidence_reference: "change-1042", notes: null,
  }));
  expect(await screen.findByText("Restore test evidence recorded.")).toBeInTheDocument();
  expect(screen.getByText(/Finance VM/)).toBeInTheDocument();
});
