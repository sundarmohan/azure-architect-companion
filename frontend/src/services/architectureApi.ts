import type { Architecture, ArchitectureSnapshot, ArchitectureVersion, Dependency, Relationship, Resource, ResourceInput, ResourceUpdate } from '../models/architecture'
import type { CatalogListResponse, CatalogResourceDetail } from '../models/catalog'
import type { AzureConnectionStatus, AzurePreflightResult, AzureSnapshotSummary, ComplianceResult, ConformanceAssessment, DependencyAnalysis, DriftHistoryComparison, ValidationResult } from '../models/analysis'
import type { VersionComparison } from '../models/versioning'
import { request } from './apiClient'

export const architectureApi = {
  listArchitectures: () => request<Architecture[]>('/architectures'),
  listVersions: (architectureId: string) => request<ArchitectureVersion[]>(`/architectures/${architectureId}/versions`),
  getVersion: (architectureId: string, versionId: string) => request<ArchitectureVersion>(`/architectures/${architectureId}/versions/${versionId}`),
  listResources: (architectureId: string, versionId: string) => request<Resource[]>(`/architectures/${architectureId}/versions/${versionId}/resources`),
  listRelationships: (architectureId: string, versionId: string) => request<Relationship[]>(`/architectures/${architectureId}/versions/${versionId}/relationships`),
  listDependencies: (architectureId: string, versionId: string) => request<Dependency[]>(`/architectures/${architectureId}/versions/${versionId}/dependencies`),
  loadSnapshot: async (architecture: Architecture, version: ArchitectureVersion): Promise<ArchitectureSnapshot> => {
    const [resources, relationships, dependencies] = await Promise.all([
      architectureApi.listResources(architecture.id, version.id),
      architectureApi.listRelationships(architecture.id, version.id),
      architectureApi.listDependencies(architecture.id, version.id),
    ])
    return { architecture, version, resources, relationships, dependencies }
  },
  createResource: (architectureId: string, versionId: string, input: ResourceInput) => request<Resource>(`/architectures/${architectureId}/versions/${versionId}/resources`, { method: 'POST', body: JSON.stringify(input) }),
  updateResource: (architectureId: string, versionId: string, resourceId: string, input: ResourceUpdate) => request<Resource>(`/architectures/${architectureId}/versions/${versionId}/resources/${resourceId}`, { method: 'PUT', body: JSON.stringify(input) }),
  deleteResource: (architectureId: string, versionId: string, resourceId: string) => request<void>(`/architectures/${architectureId}/versions/${versionId}/resources/${resourceId}`, { method: 'DELETE' }),
  createRelationship: (architectureId: string, versionId: string, sourceId: string, targetId: string, relationshipType: string) => request<Relationship>(`/architectures/${architectureId}/versions/${versionId}/relationships`, { method: 'POST', body: JSON.stringify({ source_resource_id: sourceId, target_resource_id: targetId, relationship_type: relationshipType, metadata: null }) }),
  deleteRelationship: (architectureId: string, versionId: string, relationshipId: string) => request<void>(`/architectures/${architectureId}/versions/${versionId}/relationships/${relationshipId}`, { method: 'DELETE' }),
  deleteDependency: (architectureId: string, versionId: string, dependencyId: string) => request<void>(`/architectures/${architectureId}/versions/${versionId}/dependencies/${dependencyId}`, { method: 'DELETE' }),
  listCatalog: () => request<CatalogListResponse>('/catalog/resources'),
  getCatalogResource: (resourceType: string) => request<CatalogResourceDetail>(`/catalog/resources/${encodeURIComponent(resourceType)}`),
  validate: (architectureId: string, versionId: string) => request<ValidationResult>(`/architectures/${architectureId}/versions/${versionId}/validation`),
  analyzeDependencies: (architectureId: string, versionId: string) => request<DependencyAnalysis>(`/architectures/${architectureId}/versions/${versionId}/dependency-analysis`),
  evaluateCompliance: (architectureId: string, versionId: string, frameworks: string[]) => request<ComplianceResult>(`/architectures/${architectureId}/versions/${versionId}/compliance`, { method: 'POST', body: JSON.stringify({ frameworks }) }),
  createVersion: (architectureId: string, sourceVersionId: string, changeDescription: string) => request<ArchitectureVersion>(`/architectures/${architectureId}/versions`, { method: 'POST', body: JSON.stringify({ source_version_id: sourceVersionId, change_description: changeDescription }) }),
  compareVersions: (architectureId: string, fromId: string, toId: string) => request<VersionComparison>(`/architectures/${architectureId}/versions/${fromId}/compare/${toId}`),
  getAzureStatus: () => request<AzureConnectionStatus>('/azure/intelligence/status'),
  runAzurePreflight: (architectureId: string, versionId: string) => request<AzurePreflightResult>(`/architectures/${architectureId}/versions/${versionId}/azure-preflight`, { method: 'POST', body: JSON.stringify({}) }),
  listAzureSnapshots: () => request<AzureSnapshotSummary[]>('/azure/intelligence/snapshots'),
  listConformance: (architectureId: string, versionId: string) => request<ConformanceAssessment[]>(`/architectures/${architectureId}/versions/${versionId}/conformance`),
  runConformance: (architectureId: string, versionId: string, snapshotId: string) => request<ConformanceAssessment>(`/architectures/${architectureId}/versions/${versionId}/conformance`, { method: 'POST', body: JSON.stringify({ azure_snapshot_id: snapshotId }) }),
  compareConformance: (architectureId: string, versionId: string, fromId: string, toId: string) => request<DriftHistoryComparison>(`/architectures/${architectureId}/versions/${versionId}/conformance/compare/${fromId}/${toId}`),
}
