import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AssessmentWorkspace from "./AssessmentWorkspace";
import { createAssessment, getAssessment, importAssessmentFindings, listAssessments, updateAssessmentFinding } from "../services/api";

vi.mock("../services/api", () => ({
  createAssessment: vi.fn(),
  getAssessment: vi.fn(),
  importAssessmentFindings: vi.fn(),
  listAssessments: vi.fn(),
  updateAssessmentFinding: vi.fn(),
}));

const imported = {
  external_id: "review-1",
  title: "Missing security header",
  severity: "medium",
  source: "Approved external review",
  evidence: "The reviewed response omitted the expected header.",
  tool_version: "2.0",
};

const finding = {
  ...imported,
  id: "finding-1",
  status: "ready_for_retest",
  owner: "Application team",
  due_date: "2026-11-30",
  retest_note: null,
};

const assessment = {
  id: "assessment-1",
  name: "Staging review",
  environment: "staging",
  scope: "Approved staging service.",
  authorization: "Authorization record 47.",
  window_start: "2026-11-22T11:00:00Z",
  window_end: "2026-11-22T14:00:00Z",
  findings: [finding],
};

beforeEach(() => {
  vi.resetAllMocks();
  listAssessments.mockResolvedValue([assessment]);
  getAssessment.mockResolvedValue(assessment);
});

describe("Assessments and Vulnerabilities workspace", () => {
  it("lets viewers open an assessment and access the report without mutation controls", async () => {
    render(<AssessmentWorkspace canEdit={false} />);
    fireEvent.click(await screen.findByRole("button", { name: "Open Staging review" }));

    expect(await screen.findByText("Authorization record 47.")).toBeInTheDocument();
    expect(screen.getByText("Missing security header")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export assessment JSON" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New assessment" })).not.toBeInTheDocument();
    expect(screen.queryByText("Update finding")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Findings JSON")).not.toBeInTheDocument();
  });

  it("stores the recorded scope, authorization, and a timezone-qualified assessment window", async () => {
    createAssessment.mockResolvedValue(assessment);
    render(<AssessmentWorkspace canEdit />);
    await screen.findByRole("button", { name: "Open Staging review" });
    fireEvent.click(screen.getByRole("button", { name: "New assessment" }));
    fireEvent.change(screen.getByLabelText("Assessment name"), { target: { value: assessment.name } });
    fireEvent.change(screen.getByLabelText("Environment"), { target: { value: assessment.environment } });
    fireEvent.change(screen.getByLabelText("Scope and exclusions"), { target: { value: assessment.scope } });
    fireEvent.change(screen.getByLabelText("Authorization reference"), { target: { value: assessment.authorization } });
    fireEvent.change(screen.getByLabelText("Window start"), { target: { value: "2026-11-22T11:00" } });
    fireEvent.change(screen.getByLabelText("Window end"), { target: { value: "2026-11-22T14:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Create assessment" }));

    expect(await screen.findByRole("heading", { name: assessment.name })).toBeInTheDocument();
    expect(createAssessment).toHaveBeenCalledWith({
      name: assessment.name, environment: assessment.environment, scope: assessment.scope,
      authorization: assessment.authorization,
      window_start: new Date("2026-11-22T11:00").toISOString(),
      window_end: new Date("2026-11-22T14:00").toISOString(),
    });
  });

  it("imports reviewed findings and reports duplicates", async () => {
    importAssessmentFindings.mockResolvedValue({ inserted: 1, duplicates: 1 });
    render(<AssessmentWorkspace canEdit />);
    fireEvent.click(await screen.findByRole("button", { name: "Open Staging review" }));
    fireEvent.change(await screen.findByLabelText("Findings JSON"), { target: { value: JSON.stringify([imported, imported]) } });
    fireEvent.click(screen.getByRole("button", { name: "Import findings" }));

    expect(await screen.findByText("Imported 1 · Duplicates skipped 1")).toBeInTheDocument();
    expect(importAssessmentFindings).toHaveBeenCalledWith(assessment.id, { findings: [imported, imported] });
    expect(getAssessment).toHaveBeenCalledTimes(2);
  });

  it("requires a retest note before closing a finding", async () => {
    updateAssessmentFinding.mockResolvedValue({ ...finding, status: "closed", retest_note: "Rechecked." });
    render(<AssessmentWorkspace canEdit />);
    fireEvent.click(await screen.findByRole("button", { name: "Open Staging review" }));
    fireEvent.click(await screen.findByText("Update finding"));
    fireEvent.change(screen.getByLabelText("Finding status"), { target: { value: "closed" } });
    fireEvent.click(screen.getByRole("button", { name: "Save finding" }));
    expect(await screen.findByText("Enter a retest note before closing the finding.")).toBeInTheDocument();
    expect(updateAssessmentFinding).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Retest note"), { target: { value: "Rechecked." } });
    fireEvent.click(screen.getByRole("button", { name: "Save finding" }));
    expect(await screen.findByText("Finding updated.")).toBeInTheDocument();
    expect(updateAssessmentFinding).toHaveBeenCalledWith(assessment.id, finding.id, {
      status: "closed", owner: finding.owner, due_date: finding.due_date, retest_note: "Rechecked.",
    });
  });
});
