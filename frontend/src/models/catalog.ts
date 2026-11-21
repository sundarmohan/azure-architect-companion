export interface JsonSchemaProperty {
  type?: 'string' | 'number' | 'integer' | 'boolean' | 'object' | 'array'
  title?: string
  description?: string
  enum?: Array<string | number>
  default?: unknown
  minimum?: number
  maximum?: number
}

export interface CatalogResource {
  id: string
  provider: string
  resource_type: string
  display_name: string
  category: string
  description: string | null
  version: string
  enabled: boolean
  properties_schema: {
    type?: string
    required?: string[]
    properties?: Record<string, JsonSchemaProperty>
  } | null
  default_properties: Record<string, unknown> | null
  terraform_mapping: Record<string, unknown> | null
  metadata: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface CatalogResourceDetail extends CatalogResource {
  required_dependencies: CatalogDependency[]
  recommended_dependencies: CatalogDependency[]
  optional_dependencies: CatalogDependency[]
  valid_parent_types: string[]
  valid_child_types: string[]
  networking_requirements: string[]
  security_requirements: string[]
  monitoring_requirements: string[]
  backup_requirements: string[]
}

export interface CatalogDependency {
  id: string
  depends_on_resource_type: string
  dependency_classification: 'REQUIRED' | 'RECOMMENDED' | 'OPTIONAL'
  reason: string | null
  created_at: string
}

export interface CatalogListResponse {
  total: number
  resources: CatalogResource[]
}
