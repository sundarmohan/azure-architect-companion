export interface ValidationFinding {
  architecture_id: string
  architecture_version_id: string
  severity: 'ERROR' | 'WARNING' | 'INFO'
  category: 'RESOURCE' | 'HIERARCHY' | 'DEPENDENCY' | 'RELATIONSHIP' | 'CATALOG'
  code: string
  message: string
  resource_id: string | null
  related_resource_id: string | null
  details: Record<string, unknown> | null
}

export interface ValidationResult {
  architecture_id: string
  architecture_version_id: string
  status: 'VALID' | 'INVALID'
  error_count: number
  warning_count: number
  info_count: number
  total_findings: number
  findings: ValidationFinding[]
}

export interface ComplianceFinding {
  control_code: string
  title: string
  category: string
  outcome: 'PASS' | 'FAIL' | 'WARNING' | 'RECOMMENDATION' | 'NOT_EVALUATED'
  policy_level: 'BLOCK' | 'REQUIRED' | 'RECOMMENDATION'
  message: string
  resource_id: string | null
}

export interface ComplianceEvaluation {
  framework_name: string
  framework_version: string
  overall_status: string
  total_controls: number
  findings: ComplianceFinding[]
}

export interface ComplianceResult {
  architecture_id: string
  architecture_version_id: string
  requested_frameworks: string[]
  evaluations: ComplianceEvaluation[]
  timestamp: string
}

export interface DependencyFinding {
  source_resource_id: string
  source_resource_key: string
  source_resource_type: string
  dependency_resource_type: string | null
  classification: 'REQUIRED' | 'RECOMMENDED' | 'OPTIONAL' | 'UNKNOWN'
  status: string
  reason: string | null
}

export interface DependencyAnalysis {
  architecture_id: string
  architecture_version_id: string
  total_findings: number
  required_findings: number
  recommended_findings: number
  optional_findings: number
  satisfied_count: number
  missing_count: number
  findings: DependencyFinding[]
}

export interface AzureConnectionStatus {
  status: 'CONNECTED' | 'UNAVAILABLE' | 'AUTHENTICATION_FAILED' | 'AUTHORIZATION_FAILED' | 'TIMEOUT' | 'CONFIGURATION_ERROR'
  tenant_id: string | null
  subscription_id: string | null
  message: string
  error_code?: string | null
}

export interface AzurePreflightFinding {
  code: string
  severity: 'ERROR' | 'WARNING' | 'INFO'
  message: string
  resource_id: string | null
  resource_key: string | null
  details: Record<string, unknown>
}

export interface AzurePreflightResult {
  id: string
  architecture_id: string
  architecture_version_id: string
  azure_snapshot_id: string
  architecture_snapshot_hash: string
  status: 'PASSED' | 'FAILED' | 'UNKNOWN'
  findings: AzurePreflightFinding[]
  result_hash: string
  created_at: string
}

export interface AzureSnapshotSummary {
  id: string
  snapshot_sequence: number
  snapshot_hash: string
  subscription_id: string
  retrieved_at: string
  expires_at: string
  fresh: boolean
  freshness: 'FRESH' | 'STALE'
}

export interface ConformanceFinding {
  id: string
  finding_key: string
  resource_key: string | null
  resource_type: string | null
  category: string
  severity: 'ERROR' | 'WARNING' | 'INFO'
  status: 'CONFORMANT' | 'MODIFIED' | 'MISSING' | 'UNEXPECTED' | 'UNKNOWN'
  desired_value_safe: unknown
  actual_value_safe: unknown
  property_path: string | null
  explanation: string
  evidence: Record<string, unknown>
}

export interface ConformanceAssessment {
  id: string
  architecture_id: string
  architecture_version_id: string
  azure_snapshot_id: string
  terraform_execution_id: string | null
  architecture_snapshot_hash: string
  azure_snapshot_hash: string
  engine_version: string
  comparison_hash: string
  overall_status: 'CONFORMANT' | 'DRIFTED' | 'PARTIAL' | 'UNKNOWN' | 'ERROR'
  summary: { conformant: number; modified: number; missing: number; unexpected: number; unknown: number; total_findings: number }
  findings: ConformanceFinding[]
  created_at: string
}

export interface DriftHistoryComparison {
  from_assessment_id: string
  to_assessment_id: string
  new_drift: Array<Record<string, unknown>>
  resolved_drift: Array<Record<string, unknown>>
  persistent_drift: Array<Record<string, unknown>>
}
