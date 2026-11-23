import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { getAzureHealthIncidentActions, saveAzureHealthIncidentAction } from "../services/api";
import AzureIncidentActions from "./AzureIncidentActions";

vi.mock("../services/api", () => ({
  getAzureHealthIncidentActions: vi.fn(),
  saveAzureHealthIncidentAction: vi.fn(),
}));

it("records an accountable corrective action and exposes it read-only to viewers", async () => {
  const action = { id: "action", kind: "corrective", title: "Review availability configuration",
    owner: "Operations", status: "open", due_date: "2026-12-31", updated_at: "2026-11-23T12:00:00Z" };
  getAzureHealthIncidentActions.mockResolvedValue([]);
  saveAzureHealthIncidentAction.mockResolvedValue(action);
  const { rerender } = render(<AzureIncidentActions subscription="sub-a" incidentId="incident" canEdit />);

  fireEvent.click(await screen.findByText("New incident action"));
  fireEvent.change(screen.getByLabelText("Action title"), { target: { value: action.title } });
  fireEvent.change(screen.getByLabelText("Action owner"), { target: { value: action.owner } });
  fireEvent.change(screen.getByLabelText("Action due date"), { target: { value: action.due_date } });
  fireEvent.click(screen.getByRole("button", { name: "Add action" }));

  expect(await screen.findByText("Incident action added.")).toBeInTheDocument();
  expect(getAzureHealthIncidentActions).toHaveBeenCalledWith("sub-a", "incident");
  expect(saveAzureHealthIncidentAction).toHaveBeenCalledWith("sub-a", "incident", expect.any(String), {
    kind: action.kind, title: action.title, owner: action.owner, status: action.status,
    due_date: action.due_date, updated_at: null,
  });
  const list = screen.getByRole("list");
  expect(within(list).getByText(action.title)).toBeInTheDocument();

  rerender(<AzureIncidentActions subscription="sub-a" incidentId="incident" />);
  expect(screen.getByText(action.owner)).toBeInTheDocument();
  expect(screen.queryByText("New incident action")).not.toBeInTheDocument();
  expect(screen.queryByText(`Edit ${action.title}`)).not.toBeInTheDocument();
});
