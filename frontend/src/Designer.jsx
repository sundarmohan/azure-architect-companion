import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  addEdge,
  useEdgesState,
  useNodesState,
  Handle,
  NodeResizer,
  Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  createResource,
  createRelationship,
  deleteRelationship,
  deleteResource,
  listAzureResourceCatalog,
  listAzureResourceCapabilities,
  listAzureResourceConfigurations,
  listResources,
  listRelationships,
  updateResource,
  listResourceGroups,
  createResourceGroup,
  updateResourceGroup,
  deleteResourceGroup,
  listSubscriptions,
  createSubscription,
  discoverAzureResources,
  validateRelationship,
  estimateArchitectureCost,
  getSettingsOverview,
  getAzureConnectionStatus,
} from "./services/api";

const RESOURCE_ICONS = {
  user: "/azure-icons/user.svg",
  firewall: "/azure-icons/firewall.svg",
  vnet: "/azure-icons/vnet.svg",
  subnet: "/azure-icons/subnet.svg",
  nsg: "/azure-icons/nsg.svg",
  gateway: "/azure-icons/gateway.svg",
  appservice: "/azure-icons/appservice.svg",
  appserviceplan: "/azure-icons/appserviceplan.svg",
  storage: "/azure-icons/storage.svg",
  sql: "/azure-icons/sql.svg",
  sqlserver: "/azure-icons/sqlserver.svg",
  vm: "/azure-icons/vm.svg",
  container: "/azure-icons/container.svg",
  containerenv: "/azure-icons/containerenv.svg",
  aks: "/azure-icons/aks.svg",
  keyvault: "/azure-icons/keyvault.svg",
  publicip: "/azure-icons/publicip.svg",
  natgateway: "/azure-icons/natgateway.svg",
  vpn: "/azure-icons/vpn.svg",
  bastion: "/azure-icons/bastion.svg",
  privateendpoint: "/azure-icons/privateendpoint.svg",
  loganalytics: "/azure-icons/loganalytics.svg",
};

const CATEGORY_ORDER = [
  "Networking",
  "Compute",
  "Containers",
  "Database",
  "Storage",
  "Security",
  "Management",
  "Identity",
  "Other",
];

const CATEGORY_LABELS = {
  Database: "Databases",
  Security: "Security & Identity",
  Management: "Management & Governance",
};

const EDGE_STYLE_BY_TYPE = {
  connects_to: { stroke: "#3a64c8", strokeWidth: 2 },
  contains: { stroke: "#5b7f2a", strokeWidth: 2, strokeDasharray: "4 2" },
  depends_on: { stroke: "#8d4b12", strokeWidth: 2 },
  deployed_in: { stroke: "#7a3fa0", strokeWidth: 2, strokeDasharray: "2 3" },
  integrated_with: { stroke: "#1b7f74", strokeWidth: 2 },
};

const RELATIONSHIP_PRIORITY = [
  "connects_to",
  "depends_on",
  "integrated_with",
  "deployed_in",
  "contains",
];

function AzureIcon({ type, className = "" }) {
  const source = RESOURCE_ICONS[type];
  return source ? (
    <span className={`azure-service-icon azure-service-icon-${type} ${className}`}>
      <img src={source} alt="" aria-hidden="true" />
    </span>
  ) : null;
}

function ResourceNode({ data }) {
  return (
    <div className={`azure-node azure-node-${data.kind || "resource"} ${data.dropTarget ? "drop-target" : ""}`}>
      <Handle type="target" position={Position.Left} />
      <AzureIcon type={data.kind} />
      <div className="azure-node-text">
        <strong>{data.name}</strong>
        <small>{data.displayName}</small>
        {data.location ? <span className="node-meta">{data.location}</span> : null}
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

function GroupNode({ data, selected }) {
  return (
    <div className={`rg-node ${data.dropTarget ? "drop-target" : ""}`}>
      <NodeResizer
        color="#0878ca"
        isVisible={selected && !data.readOnly}
        minWidth={data.minWidth || 540}
        minHeight={data.minHeight || 420}
        handleStyle={{ width: 10, height: 10, borderRadius: 2 }}
      />
      <div className="rg-head">
        <span>▣</span>
        <div>
          <strong>{data.name}</strong>
          <small>{data.location}</small>
        </div>
      </div>
    </div>
  );
}

function VnetNode({ data }) {
  return (
    <div className={`vnet-node ${data.dropTarget ? "drop-target" : ""}`}>
      <div className="vnet-head">
        <AzureIcon type={data.kind} />
        <div>
          <strong>{data.name}</strong>
          <small>{data.displayName}</small>
        </div>
      </div>
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

function SubnetNode({ data }) {
  return (
    <div className={`subnet-node ${data.dropTarget ? "drop-target" : ""}`}>
      <div className="subnet-head">
        <AzureIcon type={data.kind} />
        <div>
          <strong>{data.name}</strong>
          <small>{data.displayName}</small>
        </div>
      </div>
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

function getNodeType(resourceType) {
  if (resourceType === "vnet") return "vnet";
  if (resourceType === "subnet") return "subnet";
  return "resource";
}

function makeDefaultName(resourceType) {
  return `${resourceType}-resource`;
}

function getAbsoluteNodePosition(node, nodeById) {
  if (!node) {
    return { x: 0, y: 0 };
  }
  if (!node.parentId) {
    return {
      x: node.position?.x || 0,
      y: node.position?.y || 0,
    };
  }

  const parent = nodeById[node.parentId];
  const parentPos = getAbsoluteNodePosition(parent, nodeById);
  return {
    x: parentPos.x + (node.position?.x || 0),
    y: parentPos.y + (node.position?.y || 0),
  };
}

export function getNodeDimensions(node) {
  return {
    width: Number(node?.measured?.width || node?.width || node?.style?.width || (node?.type === "group" ? 540 : node?.type === "vnet" ? 440 : node?.type === "subnet" ? 260 : 170)),
    height: Number(node?.measured?.height || node?.height || node?.style?.height || (node?.type === "group" ? 420 : node?.type === "vnet" ? 260 : node?.type === "subnet" ? 180 : 80)),
  };
}

export function nodeContainsPosition(node, flowPosition, nodeById) {
  const absolute = getAbsoluteNodePosition(node, nodeById);
  const { width, height } = getNodeDimensions(node);
  return flowPosition.x >= absolute.x && flowPosition.x <= absolute.x + width && flowPosition.y >= absolute.y && flowPosition.y <= absolute.y + height;
}

export function resourceGroupMinimumSize(groupId, resources, canvasNodes) {
  const groupNode = canvasNodes.find((node) => node.id === `rg:${groupId}`);
  if (!groupNode) return { width: 540, height: 420 };
  const nodeById = Object.fromEntries(canvasNodes.map((node) => [node.id, node]));
  const groupAbsolute = getAbsoluteNodePosition(groupNode, nodeById);
  let width = 540;
  let height = 420;
  resources.filter((resource) => resource.resource_group_id === groupId).forEach((resource) => {
    const node = nodeById[resource.id];
    if (!node) return;
    const absolute = getAbsoluteNodePosition(node, nodeById);
    const dimensions = getNodeDimensions(node);
    width = Math.max(width, absolute.x - groupAbsolute.x + dimensions.width + 32);
    height = Math.max(height, absolute.y - groupAbsolute.y + dimensions.height + 32);
  });
  return { width, height };
}

export function buildCanvasNodes(resourceList, groups, catalogLookup) {
  const resourcesByGroup = Object.fromEntries(
    groups.map((group) => [group.id, resourceList.filter((resource) => resource.resource_group_id === group.id)])
  );

  const groupNodes = groups.map((group, index) => {
    const members = resourcesByGroup[group.id] || [];
    const maxX = members.reduce((max, resource) => Math.max(max, (resource.position_x || 0) + (resource.resource_type === "vnet" ? 440 : resource.resource_type === "subnet" ? 260 : 170)), 0);
    const maxY = members.reduce((max, resource) => Math.max(max, (resource.position_y || 0) + (resource.resource_type === "vnet" ? 260 : resource.resource_type === "subnet" ? 180 : 80)), 0);
    const savedWidth = Number(group.properties?.canvas_width);
    const savedHeight = Number(group.properties?.canvas_height);
    return {
      id: `rg:${group.id}`,
      type: "group",
      position: {
        x: group.position_x ?? 80 + index * 640,
        y: group.position_y ?? 120,
      },
      data: {
        name: group.name,
        location: group.location,
        minWidth: Math.max(540, maxX + 32),
        minHeight: Math.max(420, maxY + 32),
      },
      style: {
        width: Number.isFinite(savedWidth) && savedWidth > 0 ? savedWidth : Math.max(540, maxX + 32),
        height: Number.isFinite(savedHeight) && savedHeight > 0 ? savedHeight : Math.max(420, maxY + 32),
        zIndex: -1,
      },
      draggable: true,
      selectable: true,
    };
  });

  const positioned = resourceList.map((resource, index) => {
    const group = groups.find((item) => item.id === resource.resource_group_id);
    const catalogItem = catalogLookup[resource.resource_type];
    const parentResource = resource.parent_resource_id
      ? resourceList.find((item) => item.id === resource.parent_resource_id)
      : null;
    const parentId =
      parentResource && (parentResource.resource_type === "subnet" || parentResource.resource_type === "vnet")
        ? parentResource.id
        : group
        ? `rg:${group.id}`
        : undefined;
    const fallback = { x: 80 + (index % 4) * 170, y: 580 + Math.floor(index / 4) * 110 };
    return {
      id: resource.id,
      type: getNodeType(resource.resource_type),
      parentId,
      extent: parentId ? "parent" : undefined,
      position: {
        x: resource.position_x ?? fallback.x,
        y: resource.position_y ?? fallback.y,
      },
      style:
        resource.resource_type === "vnet"
          ? { width: 440, height: 260, zIndex: 0 }
          : resource.resource_type === "subnet"
          ? { width: 260, height: 180, zIndex: 1 }
          : undefined,
      data: {
        name: resource.name,
        resource,
        icon: RESOURCE_ICONS[resource.resource_type] || "AZ",
        displayName: catalogItem?.display_name || resource.resource_type,
        providerType: catalogItem?.azure_provider_type || resource.azure_resource_type || "",
        location: resource.location,
        kind: resource.resource_type,
      },
    };
  });

  return [...groupNodes, ...positioned];
}

export default function Designer({ architecture, onBack, scopedAzure = false, canEdit = true, canEstimate = canEdit }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNode, setSelectedNode] = useState(null);
  const [selectedEdge, setSelectedEdge] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [resourceGroups, setResourceGroups] = useState([]);
  const [subscriptions, setSubscriptions] = useState([]);
  const [resources, setResources] = useState([]);
  const [discoverySummary, setDiscoverySummary] = useState(null);
  const [discoverySubscriptionId, setDiscoverySubscriptionId] = useState("");
  const [discoveryLoading, setDiscoveryLoading] = useState(false);
  const [azureIntegration, setAzureIntegration] = useState(null);
  const [catalog, setCatalog] = useState([]);
  const [capabilities, setCapabilities] = useState([]);
  const [configurations, setConfigurations] = useState([]);
  const [configurationDraft, setConfigurationDraft] = useState({});
  const [configurationSaving, setConfigurationSaving] = useState(false);
  const [costEstimate, setCostEstimate] = useState(null);
  const [search, setSearch] = useState("");
  const [collapsedCategories, setCollapsedCategories] = useState({});
  const [inspectorTab, setInspectorTab] = useState("properties");
  const [activeRg, setActiveRg] = useState("");
  const [dependencyPrompt, setDependencyPrompt] = useState(null);
  const [planSelectionPrompt, setPlanSelectionPrompt] = useState(null);
  const [connectSourceId, setConnectSourceId] = useState(null);
  const [dropPreview, setDropPreview] = useState([]);
  const [connectTargetIds, setConnectTargetIds] = useState([]);
  const [subscriptionModalOpen, setSubscriptionModalOpen] = useState(false);
  const [subscriptionDraft, setSubscriptionDraft] = useState({
    name: "Test Subscription",
    subscriptionId: "",
  });
  const [resourceGroupModalOpen, setResourceGroupModalOpen] = useState(false);
  const [resourceGroupDraft, setResourceGroupDraft] = useState({
    name: "rg-test",
    location: "East US",
    subscriptionId: "none",
  });
  const [renameModalOpen, setRenameModalOpen] = useState(false);
  const [renameDraft, setRenameDraft] = useState("");
  const flowRef = useRef(null);
  const suppressCatalogClickRef = useRef(false);
  const dropInFlightKeysRef = useRef(new Set());
  const latestLoadRef = useRef(0);

  const catalogByType = useMemo(
    () => Object.fromEntries(catalog.map((item) => [item.resource_type, item])),
    [catalog]
  );

  const nodeTypes = useMemo(
    () => ({
      group: GroupNode,
      resource: ResourceNode,
      vnet: VnetNode,
      subnet: SubnetNode,
    }),
    []
  );

  const categorizedCatalog = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = catalog.filter((item) => {
      if (!q) return true;
      return (
        item.display_name.toLowerCase().includes(q) ||
        item.resource_type.toLowerCase().includes(q) ||
        item.azure_provider_type.toLowerCase().includes(q) ||
        item.category.toLowerCase().includes(q) ||
        (item.aliases || []).some((alias) => alias.toLowerCase().includes(q))
      );
    });

    const byCategory = CATEGORY_ORDER.map((category) => ({
      category,
      items: filtered.filter((item) => item.category === category),
    })).filter((entry) => entry.items.length > 0);

    const uncategorized = filtered.filter((item) => !CATEGORY_ORDER.includes(item.category));
    if (uncategorized.length > 0) {
      byCategory.push({ category: "Other", items: uncategorized });
    }
    return byCategory;
  }, [catalog, search]);

  useEffect(() => {
    setInspectorTab("properties");
  }, [selectedNode?.id]);

  const selectedResource = selectedNode?.type !== "group"
    ? resources.find((item) => item.id === selectedNode?.id) || selectedNode?.data?.resource
    : null;
  const selectedConfiguration = selectedResource
    ? configurations.find((item) => item.resource_type === selectedResource.resource_type)
    : null;

  useEffect(() => {
    if (!selectedResource) {
      setConfigurationDraft({});
      return;
    }
    const draft = { ...(selectedResource.properties || {}) };
    draft.name = selectedResource.name;
    draft.location = selectedResource.location || "";
    draft.sku = selectedResource.sku || draft.sku || "";
    const planEdge = edges.find((edge) => edge.source === selectedResource.id && edge.label?.startsWith("depends_on"));
    if (selectedResource.resource_type === "appservice") draft.plan_resource_id = planEdge?.target || draft.plan_resource_id || "";
    setConfigurationDraft(draft);
  }, [selectedResource?.id, resources, edges]);

  const resourceById = useMemo(
    () => Object.fromEntries(resources.map((item) => [item.id, item])),
    [resources]
  );

  const capabilityByType = useMemo(
    () => Object.fromEntries(capabilities.map((item) => [item.resource_type, item])),
    [capabilities]
  );

  function relationshipCandidates(sourceType, targetType, physicalParent = false) {
    if (sourceType === "appservice" && targetType === "appserviceplan") return ["depends_on"];
    if (sourceType === "vnet" && targetType === "subnet") return ["contains"];
    return physicalParent ? ["contains", "deployed_in", "integrated_with"] : ["depends_on", "integrated_with", "deployed_in", "contains", "connects_to"];
  }

  const firstValidRelationship = useCallback(async (sourceId, targetId, physicalParent = false) => {
    const source = resourceById[sourceId];
    const target = resourceById[targetId];
    if (!source || !target) return null;
    for (const relationshipType of relationshipCandidates(source.resource_type, target.resource_type, physicalParent)) {
      const validation = await validateRelationship(architecture.id, {
        source_resource_id: sourceId,
        target_resource_id: targetId,
        relationship_type: relationshipType,
      });
      if (validation.valid) return { relationshipType, validation };
    }
    return null;
  }, [architecture.id, resourceById]);

  // Geometry only identifies candidate context. Azure capability and backend validation
  // decide whether that context can create a logical relationship.
  async function resolveDropContext(resourceType, flowPosition, sourceId = null) {
    const nodeById = Object.fromEntries(nodes.map((node) => [node.id, node]));
    const containing = nodes
      .filter((node) => nodeContainsPosition(node, flowPosition, nodeById))
      .sort((a, b) => {
        const aSize = getNodeDimensions(a); const bSize = getNodeDimensions(b);
        return aSize.width * aSize.height - bSize.width * bSize.height;
      });
    const definition = catalogByType[resourceType] || {};
    const capability = capabilityByType[resourceType] || {};
    const groupNode = containing.find((node) => node.type === "group");
    const vnetNode = containing.find((node) => resourceById[node.id]?.resource_type === "vnet");
    const subnetNode = containing.find((node) => resourceById[node.id]?.resource_type === "subnet");
    const planNode = containing.find((node) => resourceById[node.id]?.resource_type === "appserviceplan");
    const groupId = groupNode?.id?.replace("rg:", "") || null;

    if (resourceType === "appservice" && planNode) {
      return { groupId, targetId: planNode.id, parentResourceId: null, relationshipSourceId: sourceId, relationshipTargetId: planNode.id, physicalParent: false };
    }
    if (resourceType === "subnet" && vnetNode) {
      return { groupId, targetId: vnetNode.id, parentResourceId: vnetNode.id, relationshipSourceId: vnetNode.id, relationshipTargetId: sourceId, physicalParent: true };
    }
    const allowedParents = capability.allowed_parent_resource_types || [];
    if (subnetNode && allowedParents.includes("subnet")) {
      return { groupId, targetId: subnetNode.id, parentResourceId: subnetNode.id, relationshipSourceId: subnetNode.id, relationshipTargetId: sourceId, physicalParent: true };
    }
    // Some services support network integration without being React Flow children.
    if (subnetNode && (capability.supports_vnet_integration || definition.requires_subnet)) {
      return { groupId, targetId: subnetNode.id, parentResourceId: null, relationshipSourceId: subnetNode.id, relationshipTargetId: sourceId, physicalParent: false };
    }
    return { groupId, targetId: null, parentResourceId: null, relationshipSourceId: null, relationshipTargetId: null, physicalParent: false };
  }

  function previewTargets(resourceType) {
    const capability = capabilityByType[resourceType] || {};
    const allowedParents = capability.allowed_parent_resource_types || [];
    const targetTypes = new Set();
    if (resourceType === "subnet") targetTypes.add("vnet");
    if (resourceType === "appservice") targetTypes.add("appserviceplan");
    allowedParents.forEach((type) => targetTypes.add(type));
    if (capability.supports_vnet_integration || catalogByType[resourceType]?.requires_subnet) targetTypes.add("subnet");
    return nodes.filter((node) => {
      const type = resourceById[node.id]?.resource_type;
      return targetTypes.has(type);
    }).map((node) => node.id);
  }

  useEffect(() => {
    let cancelled = false;
    if (!connectSourceId || !resourceById[connectSourceId]) {
      setConnectTargetIds([]);
      return undefined;
    }
    Promise.all(resources.filter((resource) => resource.id !== connectSourceId).map(async (resource) => {
      const result = await firstValidRelationship(connectSourceId, resource.id, false);
      return result ? resource.id : null;
    })).then((ids) => {
      if (!cancelled) setConnectTargetIds(ids.filter(Boolean));
    }).catch((e) => {
      if (!cancelled) setError(e.message);
    });
    return () => { cancelled = true; };
  }, [connectSourceId, resources, firstValidRelationship]);

  const renderedNodes = useMemo(() => nodes.map((node) => ({
    ...node,
    ...(canEdit ? {} : { draggable: false, connectable: false, deletable: false }),
    data: {
      ...node.data,
      readOnly: !canEdit,
      dropTarget: dropPreview.includes(node.id) || connectTargetIds.includes(node.id),
    },
  })), [nodes, dropPreview, connectTargetIds, canEdit]);

  const edgeFromRelationship = useCallback((relationship) => {
    const style = EDGE_STYLE_BY_TYPE[relationship.relationship_type] || EDGE_STYLE_BY_TYPE.connects_to;
    return {
      id: relationship.id,
      source: relationship.source_resource_id,
      target: relationship.target_resource_id,
      label: relationship.status && relationship.status !== "VALID"
        ? `${relationship.relationship_type} · ${relationship.status}`
        : relationship.relationship_type,
      data: {
        relationshipKind: relationship.relationship_kind || null,
        validationStatus: relationship.status || "VALID",
      },
      style,
      markerEnd: { type: "arrowclosed" },
    };
  }, []);

  const load = useCallback(async () => {
    const loadId = latestLoadRef.current + 1;
    latestLoadRef.current = loadId;
    try {
      setError("");
      const [catalogItems, capabilityItems, configurationItems, resourceList, relationshipList, groups, subs, settings] = await Promise.all([
        listAzureResourceCatalog(),
        listAzureResourceCapabilities(),
        listAzureResourceConfigurations(),
        listResources(architecture.id),
        listRelationships(architecture.id),
        listResourceGroups(architecture.id),
        listSubscriptions(architecture.id),
        scopedAzure ? getAzureConnectionStatus() : getSettingsOverview(),
      ]);

      if (loadId !== latestLoadRef.current) {
        return;
      }

      setCatalog(catalogItems);
      setCapabilities(capabilityItems);
      setConfigurations(configurationItems);
      setResources(resourceList);
      setResourceGroups(groups);
      setSubscriptions(subs);
      setAzureIntegration((scopedAzure ? settings : settings?.azure_integration) || null);

      setDiscoverySubscriptionId((current) => {
        if (!subs.length) {
          return "";
        }
        if (current && subs.some((item) => item.id === current)) {
          return current;
        }
        return subs[0].id;
      });

      setActiveRg((current) => {
        if (!groups.length) {
          return "";
        }
        if (current && groups.some((group) => group.id === current)) {
          return current;
        }
        return groups[0].id;
      });

      const catalogLookup = Object.fromEntries(catalogItems.map((item) => [item.resource_type, item]));
      setNodes(buildCanvasNodes(resourceList, groups, catalogLookup));
      setEdges(relationshipList.map(edgeFromRelationship));
    } catch (e) {
      if (loadId === latestLoadRef.current) {
        setError(e.message);
      }
    }
  }, [architecture.id, edgeFromRelationship, scopedAzure, setEdges, setNodes]);

  useEffect(() => {
    load();
  }, [load]);

  async function ensureResourceGroup() {
    if (resourceGroups.length > 0) return resourceGroups[0];
    const defaultName = `rg-${architecture.name.toLowerCase().replaceAll(" ", "-")}-dev`;
    const created = await createResourceGroup(architecture.id, {
      name: defaultName,
      location: architecture.default_region || "East US",
      subscription_id: subscriptions[0]?.id || null,
      position_x: 80,
      position_y: 120,
    });
    setResourceGroups([created]);
    setActiveRg(created.id);
    return created;
  }

  async function createSingleResource(definition, absolutePos, options = {}) {
    const group = options.group;
    const parentResourceId = options.parentResourceId || null;
    const groupNode = group ? nodes.find((item) => item.id === `rg:${group.id}`) || null : null;
    const parentNode = parentResourceId
      ? nodes.find((item) => item.id === parentResourceId) || null
      : groupNode;
    const nodeById = Object.fromEntries(nodes.map((item) => [item.id, item]));
    const parentAbsolutePosition = parentNode
      ? getAbsoluteNodePosition(parentNode, nodeById)
      : { x: group?.position_x || 0, y: group?.position_y || 0 };
    const relativePos = parentNode || group
      ? {
          x: Math.max(24, absolutePos.x - parentAbsolutePosition.x),
          y: Math.max(56, absolutePos.y - parentAbsolutePosition.y),
        }
      : absolutePos;
    const created = await createResource(architecture.id, {
      resource_type: definition.resource_type,
      azure_resource_type: definition.azure_provider_type,
      name: options.name || makeDefaultName(definition.resource_type),
      location:
        options.location ||
        (definition.requires_location ? group?.location || architecture.default_region || null : null),
      resource_group_id: definition.requires_resource_group ? group?.id || null : null,
      parent_resource_id: parentResourceId,
      position_x: relativePos.x,
      position_y: relativePos.y,
      properties: {
        category: definition.category,
        ...(options.properties || {}),
      },
    });
    return created;
  }

  function detectMissingDependencies(definition, group) {
    const presentTypes = new Set(
      resources
        .filter((item) => (definition.requires_resource_group ? item.resource_group_id === group?.id : true))
        .map((item) => item.resource_type)
    );

    const required = definition.required_dependencies.filter((dep) => {
      if (dep === "resource_group") {
        return !group;
      }
      return !presentTypes.has(dep);
    });

    const optional = definition.optional_dependencies.filter((dep) => !presentTypes.has(dep));
    const needsLocation = definition.requires_location && !(group?.location || architecture.default_region);

    return { required, optional, needsLocation };
  }

  async function addResourceFromDefinition(definition, flowPosition) {
    const initialContext = await resolveDropContext(definition.resource_type, flowPosition);
    const targetGroupId = definition.requires_resource_group ? initialContext.groupId || activeRg || "none" : "global";
    const dropKey = `${definition.resource_type}:${targetGroupId}:${Math.round(flowPosition.x)}:${Math.round(flowPosition.y)}`;
    if (dropInFlightKeysRef.current.has(dropKey)) {
      return;
    }

    dropInFlightKeysRef.current.add(dropKey);
    try {
      const group = definition.requires_resource_group
        ? initialContext.groupId
          ? resourceGroups.find((item) => item.id === initialContext.groupId)
          : activeRg
            ? resourceGroups.find((item) => item.id === activeRg)
            : await ensureResourceGroup()
        : null;
      const missing = detectMissingDependencies(definition, group);
      const hasBlocking = missing.required.length > 0 || missing.needsLocation;

      if (hasBlocking) {
        setDependencyPrompt({
          definition,
          flowPosition,
          group,
          missing,
        });
        return;
      }

      const compatiblePlans = definition.resource_type === "appservice"
        ? resources.filter((item) => item.resource_type === "appserviceplan" && item.resource_group_id === group?.id)
        : [];
      const planAtDrop = initialContext.targetId && resourceById[initialContext.targetId]?.resource_type === "appserviceplan"
        ? resourceById[initialContext.targetId]
        : null;
      if (definition.resource_type === "appservice" && !planAtDrop && compatiblePlans.length > 1) {
        setPlanSelectionPrompt({ definition, flowPosition, group, plans: compatiblePlans });
        return;
      }

      const chosenPlan = planAtDrop || compatiblePlans[0] || null;
      const created = await createSingleResource(definition, flowPosition, {
        group,
        parentResourceId: initialContext.parentResourceId,
        properties: chosenPlan ? { plan_resource_id: chosenPlan.id } : {},
      });
      setResources((items) => items.concat(created));
      await synchronizeContext(created, flowPosition);
      if (chosenPlan) await createRelationshipIfAllowed(created.id, chosenPlan.id, ["depends_on"]);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      dropInFlightKeysRef.current.delete(dropKey);
    }
  }

  async function createRelationshipIfAllowed(sourceId, targetId, relationshipCandidates) {
    for (const relationshipType of relationshipCandidates) {
      const validation = await validateRelationship(architecture.id, {
        source_resource_id: sourceId,
        target_resource_id: targetId,
        relationship_type: relationshipType,
      });
      if (!validation.valid) {
        continue;
      }

      try {
        await createRelationship(architecture.id, {
          source_resource_id: sourceId,
          target_resource_id: targetId,
          relationship_type: relationshipType,
        });
        return true;
      } catch (e) {
        // The database uniqueness rule is authoritative. A repeated inferred
        // relationship is already satisfied, not an interaction failure.
        if (String(e.message || "").toLowerCase().includes("already exists")) return true;
        throw e;
      }
    }
    return false;
  }

  async function synchronizeContext(resource, flowPosition, previousParentId = null) {
    if (resource.properties?.discovery_managed) return;
    const context = await resolveDropContext(resource.resource_type, flowPosition, resource.id);
    const desiredParentId = context.parentResourceId || null;
    const resourceUpdate = {};
    if (desiredParentId !== resource.parent_resource_id) resourceUpdate.parent_resource_id = desiredParentId;
    if (context.groupId && context.groupId !== resource.resource_group_id) resourceUpdate.resource_group_id = context.groupId;
    const nodeById = Object.fromEntries(nodes.map((node) => [node.id, node]));
    const layoutParent = desiredParentId
      ? nodeById[desiredParentId]
      : context.groupId
        ? nodeById[`rg:${context.groupId}`]
        : null;
    const layoutParentPosition = layoutParent ? getAbsoluteNodePosition(layoutParent, nodeById) : { x: 0, y: 0 };
    resourceUpdate.position_x = layoutParent ? Math.max(24, flowPosition.x - layoutParentPosition.x) : flowPosition.x;
    resourceUpdate.position_y = layoutParent ? Math.max(56, flowPosition.y - layoutParentPosition.y) : flowPosition.y;
    if (Object.keys(resourceUpdate).length > 0) {
      await updateResource(architecture.id, resource.id, resourceUpdate);
    }

    if (context.relationshipSourceId && context.relationshipTargetId) {
      const sourceType = context.relationshipSourceId === resource.id
        ? resource.resource_type
        : resourceById[context.relationshipSourceId]?.resource_type;
      const targetType = context.relationshipTargetId === resource.id
        ? resource.resource_type
        : resourceById[context.relationshipTargetId]?.resource_type;
      if (sourceType && targetType) {
        await createRelationshipIfAllowed(
          context.relationshipSourceId,
          context.relationshipTargetId,
          relationshipCandidates(sourceType, targetType, context.physicalParent)
        );
      }
    }

    // Moving away from a physical parent only removes the hierarchy edge for
    // that old container; independent dependencies remain untouched.
    const staleIds = new Set();
    if (previousParentId && previousParentId !== desiredParentId) {
      edges.filter((edge) => edge.source === previousParentId && edge.target === resource.id && ["contains", "deployed_in"].some((type) => edge.label?.startsWith(type))).forEach((edge) => staleIds.add(edge.id));
    }
    // Associations inferred from subnet context do not always use parent_resource_id.
    // Replace only subnet-context edges when the target subnet changes.
    edges.filter((edge) => edge.target === resource.id && resourceById[edge.source]?.resource_type === "subnet" && edge.source !== context.relationshipSourceId && ["contains", "deployed_in", "integrated_with"].some((type) => edge.label?.startsWith(type))).forEach((edge) => staleIds.add(edge.id));
    if (staleIds.size) await Promise.all([...staleIds].map((id) => deleteRelationship(architecture.id, id)));
    return context;
  }

  function releaseNodeForContextMove(node) {
    if (node.type === "group" || !node.parentId) return;
    const nodeById = Object.fromEntries(nodes.map((item) => [item.id, item]));
    const absolute = node.positionAbsolute || getAbsoluteNodePosition(node, nodeById);
    setNodes((current) => current.map((item) => item.id === node.id
      ? { ...item, parentId: undefined, extent: undefined, position: absolute }
      : item));
  }
  async function autoCreateDependencies(promptState) {
    const { definition, flowPosition } = promptState;
    try {
      const group = definition.requires_resource_group
        ? activeRg
          ? resourceGroups.find((item) => item.id === activeRg)
          : await ensureResourceGroup()
        : null;

      const createdDeps = [];
      let vnetResource = resources.find((item) => item.resource_type === "vnet" && item.resource_group_id === group?.id) || null;
      let subnetResource = resources.find((item) => item.resource_type === "subnet" && item.resource_group_id === group?.id) || null;

      for (let i = 0; i < definition.required_dependencies.length; i += 1) {
        const dependencyType = definition.required_dependencies[i];
        if (dependencyType === "resource_group") {
          continue;
        }
        const existing = resources.find((item) => item.resource_type === dependencyType && item.resource_group_id === group?.id);
        if (existing) {
          if (dependencyType === "vnet") vnetResource = existing;
          if (dependencyType === "subnet") subnetResource = existing;
          continue;
        }

        const dependencyDefinition = catalogByType[dependencyType];
        if (!dependencyDefinition) {
          continue;
        }

        const depPos = {
          x: flowPosition.x - 260 + i * 120,
          y: flowPosition.y + 30 + i * 35,
        };

        const parentResourceId = dependencyType === "subnet" ? vnetResource?.id || null : null;
        const createdDep = await createSingleResource(dependencyDefinition, depPos, {
          group,
          parentResourceId,
          name: makeDefaultName(dependencyType),
        });
        createdDeps.push(createdDep);

        if (dependencyType === "vnet") vnetResource = createdDep;
        if (dependencyType === "subnet") subnetResource = createdDep;
      }

      const baseParent = definition.requires_subnet ? subnetResource?.id || null : definition.resource_type === "subnet" ? vnetResource?.id || null : null;
      const baseResource = await createSingleResource(definition, flowPosition, {
        group,
        parentResourceId: baseParent,
        name: makeDefaultName(definition.resource_type),
      });

      const allCreated = [...createdDeps, baseResource];
      setResources((items) => items.concat(allCreated));

      for (const dep of createdDeps) {
        await createRelationshipIfAllowed(baseResource.id, dep.id, [
          "depends_on",
          "connects_to",
          "integrated_with",
        ]);
      }

      if (baseParent) {
        await createRelationshipIfAllowed(baseParent, baseResource.id, [
          "contains",
          "connects_to",
        ]);
      }

      setDependencyPrompt(null);
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  async function continueWithoutOptional(promptState) {
    try {
      const { definition, flowPosition } = promptState;
      const group = definition.requires_resource_group
        ? activeRg
          ? resourceGroups.find((item) => item.id === activeRg)
          : await ensureResourceGroup()
        : null;
      const created = await createSingleResource(definition, flowPosition, { group });
      setResources((items) => items.concat(created));
      setDependencyPrompt(null);
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  async function createAppServiceForPlan(promptState, plan) {
    try {
      const created = await createSingleResource(promptState.definition, promptState.flowPosition, {
        group: promptState.group,
        properties: { plan_resource_id: plan.id },
      });
      setResources((items) => items.concat(created));
      await createRelationshipIfAllowed(created.id, plan.id, ["depends_on"]);
      setPlanSelectionPrompt(null);
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  const onConnect = useCallback(
    async (params) => {
      try {
        const source = resourceById[params.source];
        const target = resourceById[params.target];
        const selected = await firstValidRelationship(params.source, params.target, false);
        if (!selected) {
          setError("These resources cannot be connected in this architecture");
          return;
        }
        await createRelationshipIfAllowed(params.source, params.target, [selected.relationshipType]);
        if (selected.validation.status && selected.validation.status !== "VALID") setError(selected.validation.reason || `${selected.validation.status} Azure relationship`);
        await load();
      } catch (e) {
        setError(e.message);
      }
    },
    [firstValidRelationship, createRelationshipIfAllowed, load, resourceById]
  );

  function openCreateSubscriptionModal() {
    setSubscriptionDraft({
      name: "Test Subscription",
      subscriptionId: azureIntegration?.configured_subscription_id || "",
    });
    setSubscriptionModalOpen(true);
  }

  async function submitCreateSubscription() {
    const name = (subscriptionDraft.name || "").trim();
    if (!name) {
      setError("Subscription name is required");
      return;
    }

    try {
      const created = await createSubscription(architecture.id, {
        name,
        subscription_id: (subscriptionDraft.subscriptionId || "").trim() || null,
      });
      setSubscriptions((items) => items.concat(created));
      setDiscoverySubscriptionId((current) => current || created.id);
      setSubscriptionModalOpen(false);
    } catch (e) {
      setError(e.message);
    }
  }

  async function discoverSubscriptionResources() {
    if (!discoverySubscriptionId) {
      setError("Select a subscription before discovery");
      return;
    }

    setDiscoveryLoading(true);
    setError("");
    try {
      const summary = await discoverAzureResources(architecture.id, {
        subscription_id: discoverySubscriptionId,
      });
      setDiscoverySummary(summary);
      if (!summary.success && summary.message) {
        setError(summary.message);
      }
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setDiscoveryLoading(false);
    }
  }

  function openCreateResourceGroupModal() {
    setResourceGroupDraft({
      name: "rg-test",
      location: "East US",
      subscriptionId: subscriptions[0]?.id || "none",
    });
    setResourceGroupModalOpen(true);
  }

  async function submitCreateResourceGroup() {
    const name = (resourceGroupDraft.name || "").trim();
    const location = (resourceGroupDraft.location || "").trim();
    if (!name) {
      setError("Resource group name is required");
      return;
    }
    if (!location) {
      setError("Resource group location is required");
      return;
    }

    const subscriptionId = resourceGroupDraft.subscriptionId !== "none"
      ? resourceGroupDraft.subscriptionId
      : null;

    try {
      const created = await createResourceGroup(architecture.id, {
        name,
        location,
        subscription_id: subscriptionId,
        position_x: 80 + resourceGroups.length * 620,
        position_y: 120,
      });
      setResourceGroups((items) => items.concat(created));
      setActiveRg(created.id);
      setResourceGroupModalOpen(false);
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  async function saveLayout() {
    setSaving(true);
    setError("");
    try {
      const resourceUpdates = nodes
        .filter((item) => item.type !== "group")
        .map((item) => {
          const existing = resourceById[item.id];
          const nextParentId =
            item.parentId && !item.parentId.startsWith("rg:")
              ? item.parentId
              : null;
          return updateResource(architecture.id, item.id, {
            position_x: item.position.x,
            position_y: item.position.y,
            parent_resource_id: nextParentId,
          });
        });

      const groupUpdates = nodes
        .filter((item) => item.type === "group")
        .map((item) => {
          const groupId = item.id.replace("rg:", "");
          const group = resourceGroups.find((candidate) => candidate.id === groupId);
          const minimum = resourceGroupMinimumSize(groupId, resources, nodes);
          const dimensions = getNodeDimensions(item);
          return updateResourceGroup(architecture.id, groupId, {
            position_x: item.position.x,
            position_y: item.position.y,
            properties: {
              ...(group?.properties || {}),
              canvas_width: Math.max(minimum.width, dimensions.width),
              canvas_height: Math.max(minimum.height, dimensions.height),
            },
          });
        });

      await Promise.all([...resourceUpdates, ...groupUpdates]);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  function autoLayout() {
    const layerOrder = { foundation: 0, edge: 1, compute: 2, data: 3 };
    const capabilityByType = Object.fromEntries(capabilities.map((item) => [item.resource_type, item]));
    const childrenByParent = {};
    resources.forEach((resource) => {
      if (resource.parent_resource_id) {
        childrenByParent[resource.parent_resource_id] = (childrenByParent[resource.parent_resource_id] || []).concat(resource);
      }
    });
    const counters = {};
    setNodes((current) => current.map((node) => {
      if (node.type === "group") return node;
      const resource = resourceById[node.id];
      const parent = resource?.parent_resource_id;
      const layer = capabilityByType[resource?.resource_type]?.layout_layer || "compute";
      const index = counters[layer] || 0;
      counters[layer] = index + 1;
      if (parent) {
        const childIndex = (childrenByParent[parent] || []).findIndex((item) => item.id === resource.id);
        return { ...node, position: { x: 48 + (childIndex % 3) * 210, y: 70 + Math.floor(childIndex / 3) * 150 } };
      }
      return { ...node, position: { x: 80 + (layerOrder[layer] || 0) * 300, y: 80 + index * 150 } };
    }));
  }

  function openRenameModal() {
    if (!selectedNode || selectedNode.type === "group") return;
    setRenameDraft(selectedNode.data.name || "");
    setRenameModalOpen(true);
  }

  async function submitRenameSelectedResource() {
    if (!selectedNode || selectedNode.type === "group") return;
    const nextName = (renameDraft || "").trim();
    if (!nextName) {
      setError("Resource name is required");
      return;
    }
    try {
      const updated = await updateResource(architecture.id, selectedNode.id, { name: nextName });
      setResources((items) => items.map((item) => (item.id === updated.id ? updated : item)));
      setRenameModalOpen(false);
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  async function deleteSelected() {
    try {
      if (selectedEdge) {
        await deleteRelationship(architecture.id, selectedEdge.id);
        setSelectedEdge(null);
        await load();
        return;
      }
      if (selectedNode?.type === "group") {
        const groupId = selectedNode.id.replace("rg:", "");
        await deleteResourceGroup(architecture.id, groupId);
        if (activeRg === groupId) {
          setActiveRg("");
        }
        setSelectedNode(null);
        await load();
        return;
      }
      if (selectedNode) {
        await deleteResource(architecture.id, selectedNode.id);
        setSelectedNode(null);
        await load();
      }
    } catch (e) {
      setError(e.message);
    }
  }

  function optionsForField(field) {
    const sourceTypes = {
      plan_resource_id: ["appserviceplan"],
      vnet_resource_id: ["vnet"],
      subnet_resource_id: ["subnet"],
      public_ip_resource_id: ["publicip"],
      key_vault_resource_id: ["keyvault"],
      server_resource_id: ["sqlserver"],
      network_security_group_resource_id: ["nsg"],
    }[field.name];
    return sourceTypes ? resources.filter((item) => sourceTypes.includes(item.resource_type)) : [];
  }

  function setConfigurationValue(field, value) {
    setConfigurationDraft((current) => ({ ...current, [field.name]: value }));
  }

  async function saveConfiguration() {
    if (!selectedResource || !selectedConfiguration) return;
    setConfigurationSaving(true);
    setError("");
    try {
      const properties = { ...(selectedResource.properties || {}) };
      for (const field of selectedConfiguration.fields) {
        if (!field.storage_key.startsWith("__")) properties[field.storage_key] = configurationDraft[field.name];
      }
      const update = {
        properties,
        name: configurationDraft.name || selectedResource.name,
        location: configurationDraft.location || null,
      };
      if (Object.prototype.hasOwnProperty.call(configurationDraft, "sku")) update.sku = configurationDraft.sku || null;
      await updateResource(architecture.id, selectedResource.id, update);

      if (selectedResource.resource_type === "appservice" && configurationDraft.plan_resource_id) {
        const currentPlanEdges = edges.filter((edge) => edge.source === selectedResource.id && edge.label?.startsWith("depends_on"));
        const currentPlanId = currentPlanEdges[0]?.target;
        if (currentPlanId !== configurationDraft.plan_resource_id) {
          await Promise.all(currentPlanEdges.map((edge) => deleteRelationship(architecture.id, edge.id)));
          const validation = await validateRelationship(architecture.id, {
            source_resource_id: selectedResource.id,
            target_resource_id: configurationDraft.plan_resource_id,
            relationship_type: "depends_on",
          });
          if (!validation.valid) throw new Error(validation.reason || "The selected App Service Plan is not compatible");
          await createRelationship(architecture.id, {
            source_resource_id: selectedResource.id,
            target_resource_id: configurationDraft.plan_resource_id,
            relationship_type: "depends_on",
          });
        }
      }
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setConfigurationSaving(false);
    }
  }

  async function loadCostEstimate() {
    try {
      setCostEstimate(await estimateArchitectureCost(architecture.id, { region: selectedResource?.location || undefined }));
    } catch (e) {
      setCostEstimate({ error: e.message });
    }
  }

  function renderConfigurationField(field) {
    const value = configurationDraft[field.name] ?? "";
    const options = optionsForField(field);
    const disabled = !canEdit || Boolean(selectedResource?.properties?.discovery_managed) || field.read_only || (field.depends_on && !configurationDraft[field.depends_on]);
    if (field.field_type === "boolean") {
      return <input type="checkbox" checked={Boolean(value)} disabled={disabled} onChange={(event) => setConfigurationValue(field, event.target.checked)} />;
    }
    if (field.field_type === "select") {
      return <select value={value} disabled={disabled} onChange={(event) => setConfigurationValue(field, event.target.value)}><option value="">Not set</option>{field.options.map((option) => <option key={option} value={option}>{option}</option>)}</select>;
    }
    if (field.field_type === "searchable_select") {
      return <select value={value} disabled={disabled} onChange={(event) => setConfigurationValue(field, event.target.value)}><option value="">Not assigned</option>{options.map((option) => <option key={option.id} value={option.id}>{option.name} ({option.id.slice(0, 8)})</option>)}</select>;
    }
    if (field.field_type === "multi_select") {
      return <input value={Array.isArray(value) ? value.join(", ") : value} disabled={disabled} onChange={(event) => setConfigurationValue(field, event.target.value.split(",").map((item) => item.trim()).filter(Boolean))} placeholder="Comma-separated values" />;
    }
    if (field.field_type === "structured_object" || field.field_type === "tags") {
      return <textarea value={typeof value === "object" ? JSON.stringify(value) : value} disabled={disabled} onChange={(event) => { try { setConfigurationValue(field, JSON.parse(event.target.value || "{}")); } catch { setConfigurationValue(field, event.target.value); } }} />;
    }
    return <input type={field.field_type === "number" ? "number" : "text"} value={value} disabled={disabled} onChange={(event) => setConfigurationValue(field, event.target.value)} />;
  }

  return (
    <div className="studio">
      <aside className="palette">
        <div className="studio-head">
          <button className="back-button" onClick={onBack}>← Design details</button>
          <h2>Azure Resources</h2>
          {canEdit && <p>Drag a service onto the canvas to design your topology.</p>}
        </div>

        <div className="hierarchy-panel">
          <div className="hierarchy-title">Architecture Hierarchy</div>
          <div className="hierarchy-item">
            Azure connection: {azureIntegration?.connection_state || "unavailable"}
          </div>
          {azureIntegration?.authenticated_subscription_name ? (
            <div className="hierarchy-item">
              Authenticated subscription: {azureIntegration.authenticated_subscription_name}
            </div>
          ) : null}
          {azureIntegration?.configured_subscription_id ? (
            <div className="hierarchy-item">
              Configured subscription ID: {azureIntegration.configured_subscription_id}
            </div>
          ) : null}
          <div className="hierarchy-section">
            <b>Subscriptions</b>
            {canEdit && <button className="mini" onClick={openCreateSubscriptionModal}>+</button>}
            {subscriptions.map((item) => (
              <div className="hierarchy-item" key={item.id}>
                <div>{item.name}</div>
                <small>{item.subscription_id || "No Azure subscription ID mapped"}</small>
              </div>
            ))}
            {!scopedAzure && canEdit && <div className="discovery-controls">
              <select
                value={discoverySubscriptionId}
                onChange={(event) => setDiscoverySubscriptionId(event.target.value)}
                disabled={subscriptions.length === 0 || discoveryLoading}
              >
                {subscriptions.length === 0 ? (
                  <option value="">No subscriptions</option>
                ) : (
                  subscriptions.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))
                )}
              </select>
              <button onClick={discoverSubscriptionResources} disabled={subscriptions.length === 0 || discoveryLoading}>
                {discoveryLoading ? "Discovering..." : "Discover Azure Resources"}
              </button>
            </div>}
            {discoverySummary && (
              <div className="hierarchy-item">
                {discoverySummary.success
                  ? `Discovered ${discoverySummary.resources_discovered} resources (${discoverySummary.resources_created} new, ${discoverySummary.resources_updated} updated)`
                  : `Discovery: ${discoverySummary.connection_state}`}
                {discoverySummary.discovered_subscription_name
                  ? ` • ${discoverySummary.discovered_subscription_name}`
                  : ""}
              </div>
            )}
          </div>
          <div className="hierarchy-section">
            <b>Resource Groups</b>
            {canEdit && <button className="mini" onClick={openCreateResourceGroupModal}>+</button>}
            {resourceGroups.map((item) => (
              <button
                className={`rg-select ${activeRg === item.id ? "active" : ""}`}
                key={item.id}
                onClick={() => setActiveRg(item.id)}
              >
                <strong>{item.name}</strong>
                <small>{item.location}</small>
              </button>
            ))}
          </div>
        </div>

        <div className="palette-title">Resource catalog <span>{catalog.length}</span></div>
        <input
          className="palette-search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search Azure resources..."
          aria-label="Search Azure resources"
        />

        {categorizedCatalog.map((entry) => (
          <div key={entry.category} className="category-block">
            <button
              className="category-title"
              onClick={() => setCollapsedCategories((current) => ({ ...current, [entry.category]: !current[entry.category] }))}
              aria-expanded={!collapsedCategories[entry.category]}
            >
              <span>{CATEGORY_LABELS[entry.category] || entry.category}</span><span>{collapsedCategories[entry.category] ? "+" : "−"}</span>
            </button>
            {!collapsedCategories[entry.category] && entry.items.map((item) => (
              <button
                className="resource-btn"
                key={item.resource_type}
                draggable={canEdit}
                disabled={!canEdit}
                onDragStart={(event) => {
                  suppressCatalogClickRef.current = true;
                  event.dataTransfer.effectAllowed = "copy";
                  event.dataTransfer.setData("application/monitorai-resource", JSON.stringify(item));
                }}
                onDragEnd={() => {
                  setTimeout(() => {
                    suppressCatalogClickRef.current = false;
                  }, 0);
                }}
                onClick={() => {
                  if (suppressCatalogClickRef.current) {
                    suppressCatalogClickRef.current = false;
                    return;
                  }
                  addResourceFromDefinition(item, {
                    x: 220 + Math.random() * 80,
                    y: 220 + Math.random() * 80,
                  });
                }}
              >
                <AzureIcon type={item.resource_type} className="palette-icon" />
                <span>
                  <b>{item.display_name}</b>
                  <small>{item.azure_provider_type}</small>
                </span>
              </button>
            ))}
          </div>
        ))}
      </aside>

      <section className="canvas">
        <div className="toolbar">
          <strong>{architecture.name}</strong>
          <span>
            {saving
              ? "Saving..."
              : activeRg
              ? `Target: ${resourceGroups.find((item) => item.id === activeRg)?.name}`
              : "Create a Resource Group first"}
          </span>
          {canEdit && <>
            <button onClick={saveLayout}>Save Layout</button>
            <button onClick={autoLayout}>Auto Layout</button>
          </>}
          <button onClick={load}>Reload</button>
          {canEdit && selectedNode && selectedNode.type !== "group" && <button onClick={() => setConnectSourceId((current) => current === selectedNode.id ? null : selectedNode.id)}>{connectSourceId === selectedNode.id ? "Cancel Connect" : "Connect"}</button>}
          {canEdit && selectedNode && selectedNode.type !== "group" && <button onClick={openRenameModal}>Rename</button>}
          {canEdit && (selectedNode || selectedEdge) && <button className="danger" onClick={deleteSelected}>Delete</button>}
        </div>

        {error && <div className="canvas-error">{error}</div>}

        <ReactFlow
          nodes={renderedNodes}
          edges={edges}
          nodeTypes={nodeTypes}
          nodesDraggable={canEdit}
          nodesConnectable={canEdit}
          deleteKeyCode={canEdit ? "Backspace" : null}
          elementsSelectable
          panOnDrag
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={canEdit ? onConnect : undefined}
          onInit={(instance) => {
            flowRef.current = instance;
          }}
          onNodeClick={(_, node) => {
            if (connectSourceId && node.id !== connectSourceId) {
              if (!connectTargetIds.includes(node.id)) {
                setError("That resource is not a valid connection target");
                return;
              }
              onConnect({ source: connectSourceId, target: node.id });
              setConnectSourceId(null);
              return;
            }
            setSelectedNode(node);
            setSelectedEdge(null);
          }}
          onEdgeClick={(_, edge) => {
            setSelectedEdge(edge);
            setSelectedNode(null);
          }}
          onPaneClick={() => {
            setSelectedNode(null);
            setSelectedEdge(null);
            setConnectSourceId(null);
          }}
          onNodeDragStart={(_, node) => {
            setDropPreview(previewTargets(resourceById[node.id]?.resource_type || node.data.kind));
            releaseNodeForContextMove(node);
          }}
          onNodeDragStop={async (_, node) => {
            setDropPreview([]);
            const resource = resourceById[node.id];
            if (!resource) return;
            try {
              const flowPosition = node.positionAbsolute || getAbsoluteNodePosition(node, Object.fromEntries(nodes.map((item) => [item.id, item])));
              await synchronizeContext(resource, flowPosition, resource.parent_resource_id);
              await load();
            } catch (e) {
              setError(e.message);
            }
          }}
          fitView
          onDragOver={(event) => {
            if (!canEdit) return;
            event.preventDefault();
            event.dataTransfer.dropEffect = "copy";
            try {
              const definition = JSON.parse(event.dataTransfer.getData("application/monitorai-resource") || "{}");
              setDropPreview(previewTargets(definition.resource_type));
            } catch {
              setDropPreview([]);
            }
          }}
          onDrop={async (event) => {
            if (!canEdit) return;
            event.preventDefault();
            setDropPreview([]);
            const raw = event.dataTransfer.getData("application/monitorai-resource");
            if (!raw || !flowRef.current) return;
            let definition;
            try {
              definition = JSON.parse(raw);
            } catch {
              setError("The dropped resource definition could not be read");
              return;
            }
            const pos = flowRef.current.screenToFlowPosition({
              x: event.clientX,
              y: event.clientY,
            });
            await addResourceFromDefinition(definition, pos);
          }}
        >
          <Background />
          <Controls />
        </ReactFlow>

        {selectedNode && selectedNode.type !== "group" && (
          <aside className="floating-inspector" aria-label="Resource inspector">
            <div className="inspector-heading">
              <div className="inspector-title">
                <AzureIcon type={selectedNode.data.kind} />
                <div>
                  <strong>{selectedNode.data.displayName}</strong>
                  <small>{selectedNode.data.providerType}</small>
                </div>
              </div>
              <button className="inspector-close" onClick={() => setSelectedNode(null)} aria-label="Close inspector">×</button>
            </div>
            <div className="inspector-tabs">
              {[["properties", "Properties"], ["details", "Dependencies"], ...(canEstimate ? [["cost", "Cost"]] : [])].map(([value, label]) => (
                <button key={value} className={inspectorTab === value ? "active" : ""} onClick={() => setInspectorTab(value)}>{label}</button>
              ))}
            </div>
            {inspectorTab === "properties" ? (
              <div className="inspector-body">
                <div className="inspector-mode">{selectedResource?.properties?.discovery_managed ? "Live Azure resource: metadata is read-only where applicable" : "Designed resource: changes represent desired configuration"}</div>
                <div className="prop-row"><span>Resource type</span><strong>{selectedNode.data.providerType || selectedNode.data.kind}</strong></div>
                <div className="prop-row"><span>Resource ID</span><code>{selectedNode.id}</code></div>
                <div className="prop-row"><span>Resource group</span><strong>{resourceGroups.find((group) => group.id === selectedResource.resource_group_id)?.name || "Not assigned"}</strong></div>
                <div className="prop-row"><span>Parent resource</span><strong>{resourceById[selectedResource.parent_resource_id]?.name || "None"}</strong></div>
                {Object.entries((selectedConfiguration?.fields || []).reduce((groups, field) => {
                  const section = field.section || "General";
                  groups[section] = (groups[section] || []).concat(field);
                  return groups;
                }, {})).map(([section, fields]) => (
                  <section className="inspector-config-section" key={section}>
                    <div className="inspector-section-label">{section}</div>
                    {fields.map((field) => (
                      <label className="inspector-field" key={field.name}>
                        <span>{field.label}{field.required ? " *" : ""}</span>
                        {renderConfigurationField(field)}
                        {field.description ? <small>{field.description}</small> : null}
                      </label>
                    ))}
                  </section>
                ))}
                {selectedConfiguration?.configuration_status === "common_properties_only" ? <p className="inspector-empty">Configuration not yet modeled for this resource type beyond common properties.</p> : null}
                {canEdit && <button className="inspector-save" onClick={saveConfiguration} disabled={configurationSaving}>{configurationSaving ? "Saving..." : "Save configuration"}</button>}
              </div>
            ) : inspectorTab === "details" ? (
              <div className="inspector-body">
                <div className="inspector-section-label">Relationships</div>
                {edges.filter((edge) => edge.source === selectedNode.id || edge.target === selectedNode.id).length === 0 ? (
                  <p className="inspector-empty">No relationships recorded for this resource.</p>
                ) : edges.filter((edge) => edge.source === selectedNode.id || edge.target === selectedNode.id).map((edge) => {
                  const otherId = edge.source === selectedNode.id ? edge.target : edge.source;
                  return <div className="relationship-item" key={edge.id}><span>{edge.source === selectedNode.id ? "Outbound" : "Inbound"}</span><strong>{resourceById[otherId]?.name || "Resource"}</strong><small>{edge.label}</small></div>;
                })}
              </div>
            ) : (
              <div className="inspector-body">
                <div className="inspector-section-label">Cost & Pricing</div>
                <p className="inspector-empty">Estimated planned cost only. This is not actual Azure billing.</p>
                <button className="inspector-save" onClick={loadCostEstimate}>Refresh estimate</button>
                {costEstimate?.error ? <p className="inspector-empty">{costEstimate.error}</p> : null}
                {costEstimate?.items?.filter((item) => item.resource_id === selectedResource.id).map((item) => <div className="prop-row" key={item.resource_id}><span>Estimated monthly</span><strong>{item.currency} {item.monthly_cost}</strong><small>{item.pricing_source}</small></div>)}
              </div>
            )}
          </aside>
        )}

        {dependencyPrompt && (
          <div className="dependency-modal">
            <h3>{dependencyPrompt.definition.display_name} requirements</h3>
            <div className="dep-list">
              <div><b>Required</b></div>
              {dependencyPrompt.missing.required.length === 0 ? <div>All required dependencies present.</div> : dependencyPrompt.missing.required.map((dep) => <div key={dep}>- {dep}</div>)}
              <div><b>Optional</b></div>
              {dependencyPrompt.missing.optional.length === 0 ? <div>No optional dependencies missing.</div> : dependencyPrompt.missing.optional.map((dep) => <div key={dep}>- {dep}</div>)}
              {dependencyPrompt.missing.needsLocation && <div>- location not set for this deployment context</div>}
            </div>
            <div className="dep-actions">
              <button onClick={() => autoCreateDependencies(dependencyPrompt)}>Create required dependencies</button>
              <button onClick={() => continueWithoutOptional(dependencyPrompt)}>Select existing / continue</button>
              <button onClick={() => setDependencyPrompt(null)}>Cancel</button>
            </div>
          </div>
        )}

        {planSelectionPrompt && (
          <div className="dependency-modal" role="dialog" aria-label="Select App Service Plan">
            <h3>Select an App Service Plan</h3>
            <div className="dep-list">Multiple compatible plans exist in this Resource Group.</div>
            <div className="dep-actions plan-selection-actions">
              {planSelectionPrompt.plans.map((plan) => (
                <button key={plan.id} onClick={() => createAppServiceForPlan(planSelectionPrompt, plan)}>{plan.name}</button>
              ))}
              <button onClick={() => setPlanSelectionPrompt(null)}>Cancel</button>
            </div>
          </div>
        )}

        {subscriptionModalOpen && (
          <div className="modal-backdrop" onClick={() => setSubscriptionModalOpen(false)}>
            <div className="modal-card" onClick={(event) => event.stopPropagation()}>
              <h3>Create Subscription</h3>
              <label htmlFor="new-subscription-name">Subscription display name</label>
              <input
                id="new-subscription-name"
                value={subscriptionDraft.name}
                onChange={(event) => setSubscriptionDraft((prev) => ({ ...prev, name: event.target.value }))}
                placeholder="Test Subscription"
              />
              <label htmlFor="new-subscription-id">Azure subscription ID (optional for design-only)</label>
              <input
                id="new-subscription-id"
                value={subscriptionDraft.subscriptionId}
                onChange={(event) => setSubscriptionDraft((prev) => ({ ...prev, subscriptionId: event.target.value }))}
                placeholder="00000000-0000-0000-0000-000000000000"
              />
              <div className="actions">
                <button className="dismiss" onClick={() => setSubscriptionModalOpen(false)}>Cancel</button>
                <button onClick={submitCreateSubscription}>Save</button>
              </div>
            </div>
          </div>
        )}

        {resourceGroupModalOpen && (
          <div className="modal-backdrop" onClick={() => setResourceGroupModalOpen(false)}>
            <div className="modal-card" onClick={(event) => event.stopPropagation()}>
              <h3>Create Resource Group</h3>
              <label htmlFor="new-rg-name">Resource group name</label>
              <input
                id="new-rg-name"
                value={resourceGroupDraft.name}
                onChange={(event) => setResourceGroupDraft((prev) => ({ ...prev, name: event.target.value }))}
                placeholder="rg-test"
              />
              <label htmlFor="new-rg-location">Azure location</label>
              <input
                id="new-rg-location"
                value={resourceGroupDraft.location}
                onChange={(event) => setResourceGroupDraft((prev) => ({ ...prev, location: event.target.value }))}
                placeholder="East US"
              />
              <label htmlFor="new-rg-subscription">Subscription</label>
              <select
                id="new-rg-subscription"
                value={resourceGroupDraft.subscriptionId}
                onChange={(event) => setResourceGroupDraft((prev) => ({ ...prev, subscriptionId: event.target.value }))}
              >
                <option value="none">None</option>
                {subscriptions.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
              <div className="actions">
                <button className="dismiss" onClick={() => setResourceGroupModalOpen(false)}>Cancel</button>
                <button onClick={submitCreateResourceGroup}>Save</button>
              </div>
            </div>
          </div>
        )}

        {renameModalOpen && (
          <div className="modal-backdrop" onClick={() => setRenameModalOpen(false)}>
            <div className="modal-card" onClick={(event) => event.stopPropagation()}>
              <h3>Rename Resource</h3>
              <label htmlFor="rename-resource-name">Resource name</label>
              <input
                id="rename-resource-name"
                value={renameDraft}
                onChange={(event) => setRenameDraft(event.target.value)}
                placeholder="Resource name"
              />
              <div className="actions">
                <button className="dismiss" onClick={() => setRenameModalOpen(false)}>Cancel</button>
                <button onClick={submitRenameSelectedResource}>Save</button>
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
