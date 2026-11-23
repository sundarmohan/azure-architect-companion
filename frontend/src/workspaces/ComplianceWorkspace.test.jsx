import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { getAzureConnectionStatus, getAzureSecurity, getComplianceReviews, saveComplianceReview } from "../services/api";
import ComplianceWorkspace from "./ComplianceWorkspace";

vi.mock("../services/api", () => ({
  getAzureConnectionStatus: vi.fn(),
  getAzureSecurity: vi.fn(),
  getComplianceReviews: vi.fn(),
  saveComplianceReview: vi.fn(),
}));

it("uses configured subscription evidence and treats missing matches as unverified", async () => {
  getComplianceReviews.mockResolvedValue([]);
  getAzureConnectionStatus.mockResolvedValue({ configured_subscription_ids: ["sub-a", "sub-b"] });
  getAzureSecurity.mockImplementation((id) => Promise.resolve(id === "sub-a" ? {
    status: "partial_failure",
    last_success_at: "2026-11-01T00:00:00Z",
    limitations: ["Sampled resource coverage"],
    findings: [
      { id: "1", code: "storage_http_allowed", source: "azure_configuration", title: "Insecure transfer", evidence: ["HTTPS required is disabled"] },
      { id: "2", code: "storage_legacy_tls", source: "azure_defender_assessments", title: "Unmapped provider finding" },
    ],
  } : {
    status: "synced",
    findings: [],
  }));

  render(<ComplianceWorkspace />);
  expect(await screen.findByText(/Review uses retained evidence/)).toBeInTheDocument();
  expect(screen.getByText("Insecure transfer")).toBeInTheDocument();
  expect(screen.queryByText("Unmapped provider finding")).not.toBeInTheDocument();
  expect(screen.getByText("Sampled resource coverage")).toBeInTheDocument();
  expect(screen.getByText("storage_http_allowed")).toBeInTheDocument();
  expect(screen.getAllByText("Unable to validate from saved findings")).toHaveLength(3);
  expect(screen.getByText("Scope and operating procedures")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Subscription"), { target: { value: "sub-b" } });
  expect((await screen.findAllByText("Unable to validate from saved findings")).length).toBeGreaterThan(0);
  expect(screen.queryByText("Insecure transfer")).not.toBeInTheDocument();
  expect(getAzureSecurity.mock.calls.map(([id]) => id)).toEqual(["sub-a", "sub-b"]);
});

it("saves a scoped manual review and corrective action", async () => {
  getAzureConnectionStatus.mockResolvedValue({ configured_subscription_ids: ["sub-a"] });
  getAzureSecurity.mockResolvedValue({ status: "not_synced", findings: [] });
  getComplianceReviews.mockResolvedValue([]);
  const payload = {
    state: "action_required", note: "Review transfer settings.", action: "Require HTTPS.",
    owner: "Operations", due_date: "2026-12-31", action_status: "planned",
  };
  saveComplianceReview.mockResolvedValue({
    ...payload, topic: "transport", evidence_at: null, updated_at: "2026-11-01T00:00:00Z",
  });
  render(<ComplianceWorkspace canEdit />);
  const topic = (await screen.findByText("Protected transport")).closest("li");
  const row = within(topic);
  fireEvent.click(await row.findByText("Review record · Unrecorded"));
  fireEvent.change(row.getByLabelText("Review state"), { target: { value: payload.state } });
  fireEvent.change(row.getByLabelText("Review notes"), { target: { value: payload.note } });
  fireEvent.change(row.getByLabelText("Corrective action"), { target: { value: payload.action } });
  fireEvent.change(row.getByLabelText("Action owner"), { target: { value: payload.owner } });
  fireEvent.change(row.getByLabelText("Action due date"), { target: { value: payload.due_date } });
  fireEvent.change(row.getByLabelText("Action status"), { target: { value: payload.action_status } });
  fireEvent.click(row.getByRole("button", { name: "Save review" }));
  expect(await row.findByText("Review saved.")).toBeInTheDocument();
  expect(saveComplianceReview).toHaveBeenCalledWith("sub-a", "transport", { ...payload, snapshot_attempt_at: null });
  expect(row.getByText(/Unavailable at review/)).toBeInTheDocument();
});
