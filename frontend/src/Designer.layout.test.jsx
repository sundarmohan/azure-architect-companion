import { describe, expect, it } from "vitest";
import {
  buildCanvasNodes,
  getNodeDimensions,
  nodeContainsPosition,
  resourceGroupMinimumSize,
} from "./Designer";

const group = {
  id: "rg-1",
  name: "rg-main",
  location: "East US",
  position_x: 80,
  position_y: 120,
  properties: {},
};

const vnet = {
  id: "vnet-1",
  resource_type: "vnet",
  name: "vnet-main",
  resource_group_id: "rg-1",
  position_x: 30,
  position_y: 60,
};

describe("Architecture Studio canvas layout", () => {
  it("uses persisted Resource Group dimensions instead of recalculating them on reload", () => {
    const nodes = buildCanvasNodes([vnet], [{ ...group, properties: { canvas_width: 900, canvas_height: 700 } }], {});
    const resourceGroup = nodes.find((node) => node.type === "group");
    expect(resourceGroup.style.width).toBe(900);
    expect(resourceGroup.style.height).toBe(700);
  });

  it("uses a child-aware minimum size for Resource Groups without saved dimensions", () => {
    const farVnet = { ...vnet, position_x: 600, position_y: 450 };
    const nodes = buildCanvasNodes([farVnet], [group], {});
    const minimum = resourceGroupMinimumSize("rg-1", [farVnet], nodes);
    expect(minimum.width).toBeGreaterThanOrEqual(600 + 440 + 32);
    expect(minimum.height).toBeGreaterThanOrEqual(450 + 260 + 32);
  });

  it("resolves containment from absolute parent-child bounds", () => {
    const nodes = buildCanvasNodes([vnet], [group], {});
    const byId = Object.fromEntries(nodes.map((node) => [node.id, node]));
    const vnetNode = byId["vnet-1"];
    expect(nodeContainsPosition(vnetNode, { x: 200, y: 240 }, byId)).toBe(true);
    expect(nodeContainsPosition(vnetNode, { x: 700, y: 700 }, byId)).toBe(false);
    expect(getNodeDimensions(vnetNode)).toEqual({ width: 440, height: 260 });
  });
});
