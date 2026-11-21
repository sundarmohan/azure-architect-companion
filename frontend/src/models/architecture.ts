export type VersionStatus = 'DRAFT' | 'ACTIVE' | 'SUPERSEDED' | 'ARCHIVED' | 'draft' | 'validated' | 'deployed'

export interface Architecture {
  id: string
  name: string
  description: string | null
  provider: string
  created_at: string
  updated_at: string
}

export interface ArchitectureVersion {
  id: string
  architecture_id: string
  version_number: string
  version_sequence: number | null
  status: VersionStatus
  parent_version_id: string | null
  change_description: string | null
  metadata: Record<string, unknown> | null
  snapshot_hash: string | null
  finalized_at: string | null
  validation_status: string | null
  compliance_status: string | null
  created_at: string
  created_by: string | null
}

export interface Resource {
  id: string
  architecture_version_id: string
  resource_key: string
  resource_type: string
  name: string
  location: string | null
  sku: Record<string, unknown> | null
  properties: Record<string, unknown> | null
  tags: Record<string, string> | null
  parent_resource_id: string | null
  created_at: string
  updated_at: string
}

export interface ResourceInput {
  resource_key: string
  resource_type: string
  name: string
  location?: string | null
  sku?: Record<string, unknown> | null
  properties?: Record<string, unknown> | null
  tags?: Record<string, string> | null
  parent_resource_id?: string | null
}

export interface ResourceUpdate {
  name?: string
  location?: string | null
  sku?: Record<string, unknown> | null
  properties?: Record<string, unknown> | null
  tags?: Record<string, string> | null
  parent_resource_id?: string | null
}

export interface Relationship {
  id: string
  architecture_version_id: string
  source_resource_id: string
  target_resource_id: string
  relationship_type: string
  metadata: Record<string, unknown> | null
}

export interface Dependency {
  id: string
  architecture_version_id: string
  resource_id: string
  depends_on_resource_id: string
  dependency_type: string
  required: boolean
  reason: string | null
}

export interface ArchitectureSnapshot {
  architecture: Architecture
  version: ArchitectureVersion
  resources: Resource[]
  relationships: Relationship[]
  dependencies: Dependency[]
}
