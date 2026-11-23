import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { getGitHubPipeline } from "../services/api";
import GitHubPipelineWorkspace from "./GitHubPipelineWorkspace";

vi.mock("../services/api", () => ({ getGitHubPipeline: vi.fn() }));

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
