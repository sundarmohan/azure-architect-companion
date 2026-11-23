import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import {
  getAzureConnectionStatus, getAzureHealthIncidents, getAzureInventory, getAzureMonitoring,
  getAzureSecurity, getComplianceReviews,
} from "../services/api";
import ReportsWorkspace from "./ReportsWorkspace";

vi.mock("../services/api", () => ({
  getAzureConnectionStatus: vi.fn(),
  getAzureHealthIncidents: vi.fn(),
  getAzureInventory: vi.fn(),
  getAzureMonitoring: vi.fn(),
  getAzureSecurity: vi.fn(),
  getComplianceReviews: vi.fn(),
}));

function readBlob(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(JSON.parse(reader.result));
    reader.onerror = reject;
    reader.readAsText(blob);
  });
}

it("exports bounded subscription evidence with unavailable sources reported and raw notes excluded", async () => {
  getAzureConnectionStatus.mockResolvedValue({ configured_subscription_ids: ["sub-one", "sub-two"] });
  getAzureInventory.mockResolvedValue({
    status: "synced", last_success_at: "2026-11-01T00:00:00Z",
    resources: Array.from({ length: 21 }, (_, i) => ({ id: `example-${i}`, type: "vm", secret: "omit me" })),
  });
  getAzureMonitoring.mockRejectedValue(new Error("omit source exception content"));
  getAzureSecurity.mockResolvedValue({
    status: "partial_failure", score: 30,
    findings: [{ code: "storage_http_allowed", severity: "high", evidence: ["omit raw evidence"] }],
  });
  getComplianceReviews.mockResolvedValue([
    { topic: "transport", state: "action_required", note: "omit reviewer note", owner: "omit owner" },
  ]);
  getAzureHealthIncidents.mockResolvedValue({
    has_next: true, incidents: [{ id: "example", status: "open", rca_note: "omit RCA note" }],
  });

  const createObjectURL = vi.fn(() => "blob:synthetic");
  vi.stubGlobal("URL", { createObjectURL, revokeObjectURL: vi.fn() });
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  try {
    render(<ReportsWorkspace />);
    fireEvent.change(await screen.findByLabelText("Subscription"), { target: { value: "sub-two" } });
    fireEvent.change(screen.getByLabelText("Report type"), { target: { value: "executive" } });
    fireEvent.click(screen.getByRole("button", { name: "Generate report" }));
    expect(await screen.findByRole("heading", { name: "Executive report" })).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(getAzureInventory).toHaveBeenCalledWith("sub-two");
    expect(getAzureHealthIncidents).toHaveBeenCalledWith("sub-two", 1);
    fireEvent.click(screen.getByRole("button", { name: "Download JSON" }));
    const data = await readBlob(createObjectURL.mock.calls[0][0]);
    expect(data.subscription_id).toBe("sub-two");
    expect(data.sources[0]).toMatchObject({ status: "synced", count: 21, truncated: true });
    expect(data.sources[0].rows).toHaveLength(20);
    expect(data.sources[1]).toEqual({
      source: "monitoring", label: "Azure Resource Health and monitoring", status: "unavailable",
    });
    expect(JSON.stringify(data)).not.toContain("omit");
  } finally {
    click.mockRestore();
    vi.unstubAllGlobals();
  }
});
