export interface FieldChange {
  category?: string
  field: string
  from: unknown
  to: unknown
}

export interface ResourceChange {
  resource_key: string
  change_type: string
  changes: FieldChange[]
}

export interface LinkChange {
  semantic_key: string
  change_type: string
  changes: FieldChange[]
}

export interface VersionComparison {
  architecture_id: string
  from_version_id: string
  to_version_id: string
  from_snapshot_hash: string
  to_snapshot_hash: string
  has_changes: boolean
  resource_changes: ResourceChange[]
  relationship_changes: LinkChange[]
  dependency_changes: LinkChange[]
  hierarchy_changes: ResourceChange[]
  summary: {
    resources: { added: string[]; removed: string[]; modified: string[]; unchanged: string[] }
    relationships: { added: number; removed: number; modified: number }
    dependencies: { added: number; removed: number; modified: number }
    counts: Record<string, number>
    total_changes: number
  }
}
