import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ResourceCatalog } from './ResourceCatalog'
import { PropertiesPanel } from './PropertiesPanel'
import { ValidationPanel } from './ValidationPanel'
import { CompliancePanel } from './CompliancePanel'
import { DependencyPanel } from './DependencyPanel'
import { VersionComparison } from './VersionComparison'
import { DeleteConfirmation } from './DeleteConfirmation'
import { SaveStatus } from './SaveStatus'
import { AzurePreflightPanel } from './AzurePreflightPanel'
import { ConformancePanel } from './ConformancePanel'
import { active, computeCatalog, draft, group, vm } from '../../test/fixtures'

const catalog = [computeCatalog, { ...computeCatalog, id: 'c3', display_name: 'Storage account', category: 'Storage', resource_type: 'catalog/storage' }]

describe('architecture components', () => {
  it('loads resource catalog items', () => {
    render(<ResourceCatalog resources={catalog} loading={false} disabled={false} />)
    expect(screen.getByText('Compute service')).toBeInTheDocument()
  })
  it('filters catalog search results', async () => {
    render(<ResourceCatalog resources={catalog} loading={false} disabled={false} />)
    await userEvent.type(screen.getByPlaceholderText('Search resources'), 'storage')
    expect(screen.queryByText('Compute service')).not.toBeInTheDocument()
    expect(screen.getByText('Storage account')).toBeInTheDocument()
  })
  it('makes catalog resources draggable for drafts', () => {
    render(<ResourceCatalog resources={catalog} loading={false} disabled={false} />)
    expect(screen.getByText('Compute service').closest('button')).toHaveAttribute('draggable', 'true')
  })
  it('writes catalog identity during drag start', () => {
    render(<ResourceCatalog resources={catalog} loading={false} disabled={false} />)
    const setData = vi.fn()
    fireEvent.dragStart(screen.getByText('Compute service').closest('button')!, { dataTransfer: { setData, effectAllowed: '' } })
    expect(setData).toHaveBeenCalledWith('application/aac-catalog-resource', expect.stringContaining('catalog/compute'))
  })
  it('opens selected resource properties', () => {
    render(<PropertiesPanel resource={vm} catalog={computeCatalog} readOnly={false} relationshipCount={1} onSave={vi.fn()} onDelete={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByLabelText('Resource name')).toHaveValue('web-vm')
  })
  it('renders schema fields without secret properties', () => {
    render(<PropertiesPanel resource={vm} catalog={computeCatalog} readOnly={false} relationshipCount={0} onSave={vi.fn()} onDelete={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByText('Size')).toBeInTheDocument()
    expect(screen.queryByText('administrator_password')).not.toBeInTheDocument()
  })
  it('submits controlled property edits', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    render(<PropertiesPanel resource={vm} catalog={computeCatalog} readOnly={false} relationshipCount={0} onSave={onSave} onDelete={vi.fn()} onClose={vi.fn()} />)
    const name = screen.getByLabelText('Resource name')
    await userEvent.clear(name)
    await userEvent.type(name, 'web-vm-02')
    await userEvent.click(screen.getByText('Apply changes'))
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ name: 'web-vm-02' }))
  })
  it('retains form state and displays save failures', async () => {
    render(<PropertiesPanel resource={vm} catalog={computeCatalog} readOnly={false} relationshipCount={0} onSave={vi.fn().mockRejectedValue(new Error('Save rejected'))} onDelete={vi.fn()} onClose={vi.fn()} />)
    await userEvent.click(screen.getByText('Apply changes'))
    expect(await screen.findByText('Save rejected')).toBeInTheDocument()
    expect(screen.getByLabelText('Resource name')).toHaveValue('web-vm')
  })
  it('renders explicit save states', () => {
    const { rerender } = render(<SaveStatus state="saving" />)
    expect(screen.getByText('Saving...')).toBeInTheDocument()
    rerender(<SaveStatus state="failed" />)
    expect(screen.getByText('Save failed')).toBeInTheDocument()
  })
  it('disables editing for immutable versions', () => {
    render(<PropertiesPanel resource={vm} catalog={computeCatalog} readOnly relationshipCount={0} onSave={vi.fn()} onDelete={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByLabelText('Resource name')).toBeDisabled()
    expect(screen.queryByText('Delete')).not.toBeInTheDocument()
  })
  it('renders validation findings', () => {
    render(<ValidationPanel loading={false} onRun={vi.fn()} result={{ architecture_id: 'a1', architecture_version_id: 'v2', status: 'INVALID', error_count: 1, warning_count: 0, info_count: 0, total_findings: 1, findings: [{ architecture_id: 'a1', architecture_version_id: 'v2', severity: 'ERROR', category: 'DEPENDENCY', code: 'MISSING', message: 'VM requires NIC', resource_id: 'r2', related_resource_id: null, details: null }] }} />)
    expect(screen.getByText('VM requires NIC')).toBeInTheDocument()
  })
  it('renders technical compliance outcomes without certification claims', () => {
    render(<CompliancePanel loading={false} onRun={vi.fn()} result={{ architecture_id: 'a1', architecture_version_id: 'v2', requested_frameworks: ['SOC2'], timestamp: '', evaluations: [{ framework_name: 'SOC2', framework_version: '1', overall_status: 'REVIEW', total_controls: 1, findings: [{ control_code: 'CC1', title: 'Encryption', category: 'DATA', outcome: 'WARNING', policy_level: 'REQUIRED', message: 'Review encryption', resource_id: null }] }] }} />)
    expect(screen.getByText('Review encryption')).toBeInTheDocument()
    expect(screen.queryByText(/certified/i)).not.toBeInTheDocument()
  })
  it('renders grouped dependency findings', () => {
    render(<DependencyPanel loading={false} onRun={vi.fn()} result={{ architecture_id: 'a1', architecture_version_id: 'v2', total_findings: 1, required_findings: 1, recommended_findings: 0, optional_findings: 0, satisfied_count: 0, missing_count: 1, findings: [{ source_resource_id: 'r2', source_resource_key: 'web-vm', source_resource_type: 'compute', dependency_resource_type: 'network/interface', classification: 'REQUIRED', status: 'MISSING', reason: 'Required networking' }] }} />)
    expect(screen.getByText('network/interface')).toBeInTheDocument()
  })
  it('renders backend version comparison results', () => {
    render(<VersionComparison versions={[active, draft]} fromId="v1" toId="v2" loading={false} onFromChange={vi.fn()} onToChange={vi.fn()} onCompare={vi.fn()} onClose={vi.fn()} result={{ architecture_id: 'a1', from_version_id: 'v1', to_version_id: 'v2', from_snapshot_hash: 'a', to_snapshot_hash: 'b', has_changes: true, resource_changes: [], relationship_changes: [], dependency_changes: [], hierarchy_changes: [], summary: { resources: { added: ['storage'], removed: [], modified: ['web-vm'], unchanged: [] }, relationships: { added: 1, removed: 0, modified: 0 }, dependencies: { added: 0, removed: 0, modified: 0 }, counts: {}, total_changes: 3 } }} />)
    expect(screen.getByText('storage')).toBeInTheDocument()
    expect(screen.getByText('web-vm')).toBeInTheDocument()
  })
  it('requires explicit delete confirmation', () => {
    const confirm = vi.fn()
    render(<DeleteConfirmation resource={group} affected={[vm]} onCancel={vi.fn()} onConfirm={confirm} />)
    expect(screen.getByText('web-vm')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Delete resource'))
    expect(confirm).toHaveBeenCalledOnce()
  })
  it('shows Azure connection state without calling Azure directly', () => {
    render(<AzurePreflightPanel connection={{ status: 'CONFIGURATION_ERROR', tenant_id: null, subscription_id: null, message: 'Azure is not configured' }} result={null} loading={false} onRun={vi.fn()} />)
    expect(screen.getByText('Azure is not configured')).toBeInTheDocument()
    expect(screen.getByText('Run preflight')).toBeDisabled()
  })
  it('renders stale Azure evidence as a backend finding', () => {
    render(<AzurePreflightPanel connection={{ status: 'CONNECTED', tenant_id: 'tenant', subscription_id: 'subscription', message: 'Connected' }} loading={false} onRun={vi.fn()} result={{ id: 'p1', architecture_id: 'a1', architecture_version_id: 'v2', azure_snapshot_id: 's1', architecture_snapshot_hash: 'architecture-hash', status: 'PASSED', result_hash: 'hash', created_at: '', findings: [{ code: 'AZURE_DATA_STALE', severity: 'WARNING', message: 'Azure availability data is stale', resource_id: null, resource_key: null, details: {} }] }} />)
    expect(screen.getByText('Azure availability data is stale')).toBeInTheDocument()
  })
  it('renders backend conformance status and drift counts', () => {
    const result = { id: 'c1', architecture_id: 'a1', architecture_version_id: 'v2', azure_snapshot_id: 's1', terraform_execution_id: null, architecture_snapshot_hash: 'a', azure_snapshot_hash: 'b', engine_version: '1', comparison_hash: 'c', overall_status: 'DRIFTED' as const, summary: { conformant: 0, modified: 1, missing: 0, unexpected: 0, unknown: 0, total_findings: 1 }, created_at: '2026-10-01T12:00:00Z', findings: [{ id: 'f1', finding_key: 'key', resource_key: 'web-vm', resource_type: 'vm', category: 'SKU_DRIFT', severity: 'ERROR' as const, status: 'MODIFIED' as const, desired_value_safe: 'D4', actual_value_safe: 'D2', property_path: 'sku.name', explanation: 'SKU differs', evidence: {} }] }
    render(<ConformancePanel snapshots={[]} snapshotId="" history={[result]} selected={result} comparison={null} loading={false} onSnapshotChange={vi.fn()} onRun={vi.fn()} onSelect={vi.fn()} onCompare={vi.fn()} />)
    expect(screen.getByText('CONFORMANCE: DRIFTED')).toBeInTheDocument()
    expect(screen.getByText(/modified: 1/i)).toBeInTheDocument()
    expect(screen.getByText(/web-vm: SKU differs/)).toBeInTheDocument()
  })
})
