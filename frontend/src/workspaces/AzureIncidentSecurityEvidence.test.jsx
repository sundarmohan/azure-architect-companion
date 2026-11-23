import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { getAzureIncidentSecurityEvidence, getAzureSecurity, linkAzureIncidentSecurityEvidence } from "../services/api";
import AzureIncidentSecurityEvidence from "./AzureIncidentSecurityEvidence";

vi.mock("../services/api", () => ({
  getAzureIncidentSecurityEvidence: vi.fn(),
  getAzureSecurity: vi.fn(),
  linkAzureIncidentSecurityEvidence: vi.fn(),
}));

it("explicitly links a saved finding and exposes the retained evidence to viewers", async () => {
  const id = "a".repeat(64);
  const timestamp = "2026-11-23T12:00:00Z";
  const saved = { id, title: "Network rule finding", code: "network_rule", source: "azure_configuration",
    resource_id: "resource", evidence: ["Recorded firewall configuration"], observed_at: timestamp };
  const link = { ...saved, finding_id: id, collected_at: timestamp, linked_at: timestamp };
  getAzureIncidentSecurityEvidence.mockResolvedValue([]);
  getAzureSecurity.mockResolvedValue({ status: "partial_failure", last_success_at: timestamp, findings: [saved] });
  linkAzureIncidentSecurityEvidence.mockResolvedValue(link);

  const { rerender } = render(<AzureIncidentSecurityEvidence subscription="sub-a" incidentId="incident" canEdit />);
  const choose = await screen.findByLabelText("Saved Security finding");
  expect(screen.getByText(/Retained Security snapshot/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Link Security finding" })).toBeDisabled();
  fireEvent.change(choose, { target: { value: id } });
  fireEvent.click(screen.getByRole("button", { name: "Link Security finding" }));

  expect(await screen.findByText("Security evidence linked.")).toBeInTheDocument();
  expect(linkAzureIncidentSecurityEvidence).toHaveBeenCalledWith("sub-a", "incident", id, timestamp);
  expect(screen.getByText("Network rule finding")).toBeInTheDocument();

  getAzureIncidentSecurityEvidence.mockResolvedValue([link]);
  rerender(<AzureIncidentSecurityEvidence subscription="sub-a" incidentId="incident" />);
  expect(await screen.findByText("Network rule finding")).toBeInTheDocument();
  expect(screen.queryByLabelText("Saved Security finding")).not.toBeInTheDocument();
});
