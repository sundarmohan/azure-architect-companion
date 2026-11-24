from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class ArchitectureBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    project: str | None = Field(default=None, min_length=1, max_length=160, pattern=r"\S")
    description: str | None = None
    provider: str = "azure"
    environment: str = "draft"
    status: str = "draft"
    default_region: str | None = None
    graph_data: dict = Field(default_factory=dict)

class ArchitectureCreate(ArchitectureBase):
    environment: str = Field(default="draft", min_length=1, max_length=50, pattern=r"\S")

class ArchitectureUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    project: str | None = Field(default=None, min_length=1, max_length=160, pattern=r"\S")
    description: str | None = None
    provider: str | None = None
    environment: str | None = Field(default=None, min_length=1, max_length=50, pattern=r"\S")
    status: str | None = None
    default_region: str | None = None
    graph_data: dict | None = None

class ArchitectureRead(ArchitectureBase):
    id: UUID
    model_config = ConfigDict(from_attributes=True)

class ResourceCreate(BaseModel):
    resource_type: str
    azure_resource_type: str | None = None
    name: str = Field(min_length=1, max_length=200)
    location: str | None = None
    parent_resource_id: UUID | None = None
    resource_group_id: UUID | None = None
    sku: str | None = None
    properties: dict = Field(default_factory=dict)
    position_x: float = 0
    position_y: float = 0

class ResourceRead(ResourceCreate):
    id: UUID
    architecture_id: UUID
    model_config = ConfigDict(from_attributes=True)

class ResourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    location: str | None = None
    parent_resource_id: UUID | None = None
    resource_group_id: UUID | None = None
    sku: str | None = None
    properties: dict | None = None
    position_x: float | None = None
    position_y: float | None = None

class RelationshipCreate(BaseModel):
    source_resource_id: UUID
    target_resource_id: UUID
    relationship_type: str = "connects_to"
    properties: dict = Field(default_factory=dict)

class RelationshipRead(RelationshipCreate):
    id: UUID
    architecture_id: UUID
    model_config = ConfigDict(from_attributes=True)


class SubscriptionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    subscription_id: str | None = None
    tenant_id: str | None = None
    environment: str = "design"
    properties: dict = Field(default_factory=dict)

class SubscriptionRead(SubscriptionCreate):
    id: UUID
    architecture_id: UUID
    model_config = ConfigDict(from_attributes=True)

class ResourceGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=100)
    subscription_id: UUID | None = None
    position_x: float = 80
    position_y: float = 120
    tags: dict = Field(default_factory=dict)
    properties: dict = Field(default_factory=dict)

class ResourceGroupRead(ResourceGroupCreate):
    id: UUID
    architecture_id: UUID
    model_config = ConfigDict(from_attributes=True)

class ResourceGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    location: str | None = Field(default=None, min_length=1, max_length=100)
    subscription_id: UUID | None = None
    position_x: float | None = None
    position_y: float | None = None
    tags: dict | None = None
    properties: dict | None = None

class DependencyRead(BaseModel):
    id: UUID
    architecture_id: UUID
    resource_type: str
    dependency_type: str
    required: bool
    auto_create_allowed: bool
    notes: str | None = None
    properties: dict
    model_config = ConfigDict(from_attributes=True)


class RelationshipValidationRequest(BaseModel):
    source_resource_id: UUID
    target_resource_id: UUID
    relationship_type: str


class RelationshipValidationRead(BaseModel):
    valid: bool
    reason: str | None = None
    status: str = "VALID"
    relationship_kind: str | None = None
    reference: str | None = None


class AzureResourceCatalogItem(BaseModel):
    resource_type: str
    display_name: str
    azure_provider_type: str
    icon: str
    category: str
    aliases: list[str] = Field(default_factory=list)
    required_dependencies: list[str] = Field(default_factory=list)
    optional_dependencies: list[str] = Field(default_factory=list)
    networking_capability: str | None = None
    requires_subnet: bool = False
    requires_resource_group: bool = True
    requires_location: bool = True
    deployable: bool = True


class AzureDiscoveryRequest(BaseModel):
    subscription_id: UUID


class AzureDiscoveredResource(BaseModel):
    azure_resource_id: str
    resource_type: str
    name: str
    resource_group_name: str | None = None
    parent_azure_resource_id: str | None = None
    action: str


class AzureDiscoveryRead(BaseModel):
    success: bool
    connection_state: str
    message: str | None = None
    architecture_id: UUID
    subscription_id: UUID
    discovered_subscription_id: str | None = None
    discovered_subscription_name: str | None = None
    discovered_subscription_state: str | None = None
    resource_groups_discovered: int = 0
    resources_discovered: int = 0
    resource_groups_created: int = 0
    resource_groups_updated: int = 0
    resources_created: int = 0
    resources_updated: int = 0
    hierarchy_links_updated: int = 0
    relationships_created: int = 0
    relationships_updated: int = 0
    unresolved_relationships: int = 0
    unsupported_resources: int = 0
    skipped_without_group: int = 0
    normalized_resources: list[AzureDiscoveredResource] = Field(default_factory=list)
