import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AzureMetricThreshold from "./AzureMetricThreshold";
import { getAzureMetricThreshold, saveAzureMetricThreshold } from "../services/api";

vi.mock("../services/api", () => ({
  getAzureMetricThreshold: vi.fn(),
  saveAzureMetricThreshold: vi.fn(),
}));

const choice = {
  resource_id: "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
  resource_name: "vm",
  metric: "Percentage CPU",
  aggregation: "average",
  unit: "Percent",
};

beforeEach(() => vi.resetAllMocks());

describe("Azure metric threshold", () => {
  it("allows an administrator to save a supported series and shows its evaluation", async () => {
    getAzureMetricThreshold.mockResolvedValue({
      threshold: null, assessment: null, choices: [choice], snapshot_status: "synced",
      last_attempt_at: "2026-11-01T00:00:00Z", last_success_at: "2026-11-01T00:00:00Z",
    });
    saveAzureMetricThreshold.mockResolvedValue({
      threshold: { ...choice, direction: "above", limit: 80 },
      assessment: { status: "breached", value: 82.5, sample_at: "2026-11-01T00:00:00Z", freshness: "recent" },
      choices: [choice], snapshot_status: "synced",
    });
    render(<AzureMetricThreshold subscription="sub" canManage />);

    expect(await screen.findByLabelText("Saved metric")).toHaveTextContent("vm · Percentage CPU · Average");
    fireEvent.change(screen.getByLabelText("Limit (Percent)"), { target: { value: "80" } });
    fireEvent.click(screen.getByRole("button", { name: "Save threshold" }));

    await waitFor(() => expect(saveAzureMetricThreshold).toHaveBeenCalledWith("sub", {
      resource_id: choice.resource_id, metric: "Percentage CPU", aggregation: "average",
      direction: "above", limit: 80,
    }));
    expect(await screen.findByText("Metric threshold saved.")).toBeInTheDocument();
    expect(screen.getByText("Breached")).toBeInTheDocument();
    expect(screen.getByText("82.5 Percent")).toBeInTheDocument();
  });

  it("keeps viewer access read-only", async () => {
    getAzureMetricThreshold.mockResolvedValue({
      threshold: { ...choice, direction: "below", limit: 10 },
      assessment: { status: "within", value: 20, sample_at: null, freshness: "retained" },
      choices: [choice], snapshot_status: "partial_failure",
    });
    render(<AzureMetricThreshold subscription="sub" />);
    expect(await screen.findByText("Within")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save threshold" })).not.toBeInTheDocument();
  });
});
