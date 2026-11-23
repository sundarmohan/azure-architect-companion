import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { getAzureActualCost, getAzureConnectionStatus } from "../services/api";
import AzureActualCostWorkspace from "./AzureActualCostWorkspace";

vi.mock("../services/api", () => ({
  getAzureActualCost: vi.fn(),
  getAzureConnectionStatus: vi.fn(),
}));

it("loads a chosen subscription and clears charges when scope changes", async () => {
  getAzureConnectionStatus.mockResolvedValue({ configured_subscription_ids: ["sub-a", "sub-b"] });
  getAzureActualCost.mockResolvedValueOnce({
    available: true,
    currency: "CAD",
    total_cost: 1.26,
    start_date: "2026-01-01",
    end_date: "2026-01-02",
    daily: [{ usage_date: "2026-01-02", cost: 1.26 }],
  }).mockResolvedValueOnce({ available: false, error: "Azure permissions are insufficient" });
  render(<AzureActualCostWorkspace />);
  const subscription = await screen.findByLabelText("Subscription");
  fireEvent.change(subscription, { target: { value: "sub-b" } });
  fireEvent.change(screen.getByLabelText("Start date (UTC)"), { target: { value: "2026-01-01" } });
  fireEvent.change(screen.getByLabelText("End date (UTC)"), { target: { value: "2026-01-02" } });
  fireEvent.click(screen.getByRole("button", { name: "Load actual cost" }));
  const charges = await screen.findByRole("table", { name: "Daily actual Azure cost" });
  expect(within(charges).getByText("2026-01-02")).toBeInTheDocument();
  expect(getAzureActualCost).toHaveBeenNthCalledWith(1, "sub-b", "2026-01-01", "2026-01-02");
  fireEvent.change(subscription, { target: { value: "sub-a" } });
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Load actual cost" }));
  expect(await screen.findByText("Azure permissions are insufficient")).toBeInTheDocument();
  expect(getAzureActualCost).toHaveBeenCalledTimes(2);
});
