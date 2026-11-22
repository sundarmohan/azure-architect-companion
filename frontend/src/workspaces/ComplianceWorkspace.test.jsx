import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { getAzureConnectionStatus, getAzureSecurity } from "../services/api";
import ComplianceWorkspace from "./ComplianceWorkspace";

vi.mock("../services/api", () => ({
  getAzureConnectionStatus: vi.fn(),
  getAzureSecurity: vi.fn(),
}));

it("uses configured subscription evidence and treats missing matches as unverified", async () => {
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
