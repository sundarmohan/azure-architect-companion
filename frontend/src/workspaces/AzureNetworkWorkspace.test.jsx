import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AzureNetworkWorkspace from "./AzureNetworkWorkspace";
import { getAzureConnectionStatus, getAzureNetwork, refreshAzureNetwork } from "../services/api";

vi.mock("../services/api", () => ({
  getAzureConnectionStatus: vi.fn(),
  getAzureNetwork: vi.fn(),
  refreshAzureNetwork: vi.fn(),
}));

vi.mock("@xyflow/react", () => ({
  Background: () => null,
  Controls: () => null,
  MarkerType: { ArrowClosed: "arrowclosed" },
  ReactFlow: ({ nodes, edges }) => <div data-testid="topology">
    {nodes.length} nodes, {edges.length} links
  </div>,
}));

const SUBSCRIPTION = "subscription-a";
const network = {
  status: "synced",
  resources: [
    { id: "vnet", name: "VNet", location: "eastus", type: "Microsoft.Network/virtualNetworks", properties: { dnsServers: ["10.0.0.4"] } },
    { id: "subnet", name: "App subnet", location: "eastus", type: "Microsoft.Network/virtualNetworks/subnets", properties: {} },
    { id: "nsg", name: "Separate NSG", location: "eastus", type: "Microsoft.Network/networkSecurityGroups", properties: {} },
  ],
  links: [{ source: "vnet", target: "subnet", kind: "contains" }],
  limitations: ["Network configuration does not provide observed traffic."],
};

beforeEach(() => {
  vi.resetAllMocks();
  getAzureConnectionStatus.mockResolvedValue({ configured_subscription_id: SUBSCRIPTION, configured_subscription_ids: [SUBSCRIPTION] });
  getAzureNetwork.mockResolvedValue(network);
});

describe("Azure network workspace", () => {
  it("renders evidence and topology only for links that Azure configuration returned", async () => {
    render(<AzureNetworkWorkspace canRefresh={false} />);
    expect(await screen.findByText("Network configuration does not provide observed traffic.")).toBeInTheDocument();
    expect(screen.getByTestId("topology")).toHaveTextContent("2 nodes, 1 links");
    const table = within(screen.getByRole("table"));
    expect(table.getByRole("cell", { name: "VNet" })).toBeInTheDocument();
    expect(table.getByRole("cell", { name: "Contains" })).toBeInTheDocument();
    expect(table.getByRole("cell", { name: "App subnet" })).toBeInTheDocument();
    expect(table.queryByRole("cell", { name: "Separate NSG" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Refresh snapshot" })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Resource"), { target: { value: "nsg" } });
    expect(screen.getByText("No configuration links were returned for this resource.")).toBeInTheDocument();
    expect(screen.queryByTestId("topology")).not.toBeInTheDocument();
  });

  it("reports a provider error while retaining the snapshot returned by refresh", async () => {
    refreshAzureNetwork.mockResolvedValue({ ...network, status: "provider_error", last_success_at: "2026-11-01T00:00:00Z" });
    render(<AzureNetworkWorkspace canRefresh />);
    await screen.findByRole("heading", { name: "VNet" });
    fireEvent.click(screen.getByRole("button", { name: "Refresh snapshot" }));
    expect(await screen.findByText("Showing the last available data.")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "App subnet" })).toBeInTheDocument();
    expect(refreshAzureNetwork).toHaveBeenCalledWith(SUBSCRIPTION);
  });
});
