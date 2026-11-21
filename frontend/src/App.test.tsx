import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { active, architecture, catalogMap, computeCatalog, draft, snapshot } from './test/fixtures'
import { ApiError } from './services/apiClient'
import type { CatalogResourceDetail } from './models/catalog'
import type { Connection } from '@xyflow/react'

vi.mock('./components/architecture/ArchitectureCanvas', () => ({ ArchitectureCanvas: ({ onConnect }: { onConnect: (connection: Connection) => void }) => <div data-testid="canvas">Canvas<button onClick={() => onConnect({ source: 'r1', target: 'r2', sourceHandle: null, targetHandle: null })}>Connect test nodes</button></div> }))
vi.mock('./services/architectureApi', () => ({
  architectureApi: {
    listArchitectures: vi.fn(), listVersions: vi.fn(), loadSnapshot: vi.fn(), listCatalog: vi.fn(), getCatalogResource: vi.fn(),
    createVersion: vi.fn(), validate: vi.fn(), analyzeDependencies: vi.fn(), evaluateCompliance: vi.fn(), compareVersions: vi.fn(),
    getAzureStatus: vi.fn(), runAzurePreflight: vi.fn(),
    listAzureSnapshots: vi.fn(), listConformance: vi.fn(), runConformance: vi.fn(), compareConformance: vi.fn(),
    createResource: vi.fn(), updateResource: vi.fn(), deleteResource: vi.fn(), createRelationship: vi.fn(), deleteRelationship: vi.fn(), deleteDependency: vi.fn(),
  },
}))

import { architectureApi } from './services/architectureApi'
const mocked = vi.mocked(architectureApi)

describe('App integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocked.listArchitectures.mockResolvedValue([architecture])
    mocked.listVersions.mockResolvedValue([active, draft])
    mocked.listCatalog.mockResolvedValue({ total: 1, resources: [computeCatalog] })
    mocked.loadSnapshot.mockResolvedValue(snapshot)
    mocked.getCatalogResource.mockImplementation(async (type) => (catalogMap as Record<string, CatalogResourceDetail>)[type] ?? computeCatalog)
    mocked.getAzureStatus.mockResolvedValue({ status: 'CONFIGURATION_ERROR', tenant_id: null, subscription_id: null, message: 'Azure tenant and subscription are not configured' })
    mocked.listAzureSnapshots.mockResolvedValue([])
    mocked.listConformance.mockResolvedValue([])
  })

  it('loads an architecture and canvas', async () => {
    render(<App />)
    expect(await screen.findByText('Production platform')).toBeInTheDocument()
    expect(await screen.findByTestId('canvas')).toBeInTheDocument()
  })

  it('version selector exposes backend versions', async () => {
    render(<App />)
    await screen.findByText('Production platform')
    expect(await screen.findByText('V1 · ACTIVE')).toBeInTheDocument()
    expect(screen.getByText('V2 · DRAFT')).toBeInTheDocument()
  })

  it('creates and switches to a new backend version', async () => {
    mocked.createVersion.mockResolvedValue({ ...draft, id: 'v3', version_sequence: 3 })
    mocked.listVersions.mockResolvedValueOnce([active, draft]).mockResolvedValueOnce([active, draft, { ...draft, id: 'v3', version_sequence: 3 }])
    render(<App />)
    await screen.findByText('Production platform')
    await userEvent.click(screen.getByText('New version'))
    await userEvent.type(screen.getByLabelText('Change description'), 'Add storage')
    await userEvent.click(screen.getByText('Create draft'))
    await waitFor(() => expect(mocked.createVersion).toHaveBeenCalledWith('a1', 'v2', 'Add storage'))
  })

  it('creates an explicitly typed relationship through the dialog', async () => {
    mocked.createRelationship.mockResolvedValue({ id: 'rel2', architecture_version_id: 'v2', source_resource_id: 'r1', target_resource_id: 'r2', relationship_type: 'routes_to', properties: {}, created_at: '' })
    mocked.validate.mockResolvedValue({ architecture_id: 'a1', architecture_version_id: 'v2', status: 'VALID', error_count: 0, warning_count: 0, info_count: 0, total_findings: 0, findings: [] })
    render(<App />)
    await screen.findByText('Production platform')
    await userEvent.click(await screen.findByText('Connect test nodes'))
    await userEvent.type(screen.getByLabelText('Relationship type'), 'routes_to')
    await userEvent.click(screen.getByRole('button', { name: 'Create relationship' }))
    await waitFor(() => expect(mocked.createRelationship).toHaveBeenCalledWith('a1', 'v2', 'r1', 'r2', 'routes_to'))
  })

  it('shows centralized API errors', async () => {
    mocked.listArchitectures.mockRejectedValue(new ApiError(500, { code: 'HTTP_500', message: 'Service unavailable' }))
    render(<App />)
    expect(await screen.findByText('Service unavailable')).toBeInTheDocument()
  })

  it('preserves conflict actions for stale versions', async () => {
    mocked.listArchitectures.mockRejectedValue(new ApiError(409, { code: 'VERSION_STALE', message: 'Version changed' }))
    render(<App />)
    expect(await screen.findByText('Version changed')).toBeInTheDocument()
    const alert = screen.getByRole('alert')
    expect(within(alert).getByText('Reload latest')).toBeInTheDocument()
    expect(within(alert).getByText('Compare')).toBeInTheDocument()
  })

  it('runs Azure preflight through the backend API', async () => {
    mocked.getAzureStatus.mockResolvedValue({ status: 'CONNECTED', tenant_id: 'tenant', subscription_id: 'subscription', message: 'Connected' })
    mocked.runAzurePreflight.mockResolvedValue({ id: 'p1', architecture_id: 'a1', architecture_version_id: 'v2', azure_snapshot_id: 's1', architecture_snapshot_hash: 'hash', status: 'PASSED', findings: [], result_hash: 'result', created_at: '' })
    render(<App />)
    await screen.findByText('Production platform')
    await userEvent.click(screen.getByText('Azure'))
    await userEvent.click(screen.getByText('Run preflight'))
    await waitFor(() => expect(mocked.runAzurePreflight).toHaveBeenCalledWith('a1', 'v2'))
  })

  it('runs conformance against the selected normalized snapshot', async () => {
    const assessment = { id: 'c1', architecture_id: 'a1', architecture_version_id: 'v2', azure_snapshot_id: 's1', terraform_execution_id: null, architecture_snapshot_hash: 'architecture-hash', azure_snapshot_hash: 'azure-hash', engine_version: '1.0.0', comparison_hash: 'comparison-hash', overall_status: 'DRIFTED' as const, summary: { conformant: 0, modified: 1, missing: 0, unexpected: 0, unknown: 0, total_findings: 1 }, findings: [], created_at: '2025-01-01T00:00:00Z' }
    mocked.listAzureSnapshots.mockResolvedValue([{ id: 's1', snapshot_sequence: 1, snapshot_hash: 'azure-hash', subscription_id: 'subscription', retrieved_at: '2025-01-01T00:00:00Z', expires_at: '2025-01-01T01:00:00Z', fresh: true, freshness: 'FRESH' }])
    mocked.runConformance.mockResolvedValue(assessment)
    mocked.listConformance.mockResolvedValueOnce([]).mockResolvedValueOnce([assessment])
    render(<App />)
    await screen.findByText('Production platform')
    await userEvent.click(screen.getByText('Drift'))
    await screen.findByRole('option', { name: 'S1 · FRESH' })
    await userEvent.click(screen.getByText('Run check'))
    await waitFor(() => expect(mocked.runConformance).toHaveBeenCalledWith('a1', 'v2', 's1'))
    expect(await screen.findByText('CONFORMANCE: DRIFTED')).toBeInTheDocument()
  })
})
