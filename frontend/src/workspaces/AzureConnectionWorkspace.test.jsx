import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import AzureConnectionWorkspace from "./AzureConnectionWorkspace";
import { getAzureConnectionStatus } from "../services/api";

vi.mock("../services/api", () => ({
  clearAzureCredentials: vi.fn(),
  getAzureConnectionStatus: vi.fn(),
  saveAzureCredentials: vi.fn(),
  testAzureIntegration: vi.fn(),
}));

it("distinguishes saved credentials from a verified Azure connection", async () => {
  getAzureConnectionStatus.mockResolvedValue({
    enabled: true,
    connection_state: "unverified",
    configured_subscription_ids: ["subscription-a"],
    last_tested_at: null,
    last_successful_test_at: null,
  });

  render(<AzureConnectionWorkspace canManage />);

  expect(await screen.findByText("Credentials are saved but have not been verified with Azure.")).toBeInTheDocument();
  expect(screen.getByText(/Last successful verification Never/)).toBeInTheDocument();
});

it("shows the bounded failure, next action, and support reference", async () => {
  getAzureConnectionStatus.mockResolvedValue({
    enabled: true,
    connection_state: "permission_failure",
    configured_subscription_ids: ["subscription-a"],
    failure_stage: "subscription_read",
    failure_reason: "insufficient_permission",
    correlation_id: "support-reference",
  });

  render(<AzureConnectionWorkspace canManage />);

  expect(await screen.findByText(/Failed stage: subscription_read/)).toBeInTheDocument();
  expect(screen.getByText(/Grant the service principal Reader access/)).toBeInTheDocument();
  expect(screen.getByText("support-reference")).toBeInTheDocument();
});
