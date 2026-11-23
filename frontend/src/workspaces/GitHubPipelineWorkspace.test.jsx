import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { getDevSecOpsFindings, getGitHubPipeline, importDevSecOpsFindings } from "../services/api";
import GitHubPipelineWorkspace from "./GitHubPipelineWorkspace";

vi.mock("../services/api", () => ({
  getDevSecOpsFindings: vi.fn(),
  getGitHubPipeline: vi.fn(),
  importDevSecOpsFindings: vi.fn(),
}));

it("loads bounded public workflow outcomes and links to GitHub", async () => {
  getGitHubPipeline.mockResolvedValue({
    repository: "octocat/hello-world", total_count: 1, collected_at: "2026-11-01T01:00:00Z",
    runs: [{
      id: 111, name: "Build", head_branch: "main", head_sha: "a".repeat(40), event: "push",
      status: "completed", conclusion: "success", created_at: "2026-11-01T00:00:00Z",
    }],
  });
  render(<GitHubPipelineWorkspace />);
  fireEvent.change(screen.getByLabelText("Repository owner"), { target: { value: "octocat" } });
  fireEvent.change(screen.getByLabelText("Repository name"), { target: { value: "hello-world" } });
  fireEvent.click(screen.getByRole("button", { name: "Load workflow runs" }));
  expect(await screen.findByRole("link", { name: "Build" }))
    .toHaveAttribute("href", "https://github.com/octocat/hello-world/actions/runs/111");
  expect(screen.getByText("Success")).toBeInTheDocument();
  expect(getGitHubPipeline).toHaveBeenCalledWith("octocat", "hello-world");
});

it("rejects raw fields before import and refreshes the saved findings page", async () => {
  const finding = {
    owner: "octocat", repository: "hello-world", source: "approved-scanner",
    fingerprint: "a".repeat(64), category: "container", severity: "high",
  };
  getDevSecOpsFindings.mockResolvedValueOnce({ findings: [], has_next: false }).mockResolvedValueOnce({
    findings: [{ ...finding, id: "finding", recommendation: "Review the affected image." }], has_next: false,
  });
  importDevSecOpsFindings.mockResolvedValue({ inserted: 1, duplicates: 0 });

  render(<GitHubPipelineWorkspace canEdit />);
  fireEvent.click(screen.getByRole("button", { name: "Review repository findings" }));
  expect(await screen.findByText("No imported repository findings on this page.")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Import sanitized finding metadata"));
  const input = screen.getByLabelText("Finding metadata JSON");
  fireEvent.change(input, { target: { value: JSON.stringify([{ ...finding, raw_secret: "omit this fixture" }]) } });
  fireEvent.click(screen.getByRole("button", { name: "Import findings" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("supported metadata fields");
  expect(importDevSecOpsFindings).not.toHaveBeenCalled();
  fireEvent.change(input, { target: { value: JSON.stringify([finding]) } });
  fireEvent.click(screen.getByRole("button", { name: "Import findings" }));
  expect(await screen.findByText("Review the affected image.")).toBeInTheDocument();
  expect(importDevSecOpsFindings).toHaveBeenCalledWith({ findings: [finding] });
});
