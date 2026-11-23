import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AzureIncidentAttention from "./AzureIncidentAttention";
import { getAzureIncidentAttention } from "../services/api";

vi.mock("../services/api", () => ({ getAzureIncidentAttention: vi.fn() }));

const incident = {
  id: "incident-1", resource_id: "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
  created_at: "2026-11-01T00:00:00Z",
};

beforeEach(() => vi.resetAllMocks());

describe("incident attention", () => {
  it("opens exact unassigned and overdue incident records", async () => {
    const onSelect = vi.fn();
    getAzureIncidentAttention.mockResolvedValue({
      unassigned_incidents: [incident],
      overdue_actions: [{ incident: { ...incident, id: "incident-2" }, action: {
        id: "action-1", title: "Confirm recovery", owner: "Ops", due_date: "2026-10-01",
      } }],
    });
    render(<AzureIncidentAttention subscription="sub" onSelect={onSelect} />);

    fireEvent.click(await screen.findByRole("button", { name: /Review unassigned incident/ }));
    expect(onSelect).toHaveBeenLastCalledWith(incident);
    fireEvent.click(screen.getByRole("button", { name: "Review Confirm recovery" }));
    expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ id: "incident-2" }));
    expect(getAzureIncidentAttention).toHaveBeenCalledWith("sub");
  });
});
